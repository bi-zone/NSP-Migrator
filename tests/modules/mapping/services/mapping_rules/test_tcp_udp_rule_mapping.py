from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.infrastructure.cache import InMemoryTTLStore
from app.integrations.sdwan_csp_api.gateways.enums import SdwanServiceL4Proto
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanFullCatalog,
    SdwanService,
)
from app.modules.mapping.adapters.runtime_cache import RuntimeCacheMappingRepository
from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanCommand,
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.domain.entities import MappingScope
from app.modules.mapping.domain.enums import (
    MappingResultStatus,
    MappingScopeRuleOperandRole,
    MappingScopeRulesPriority,
    SdwanObjectSelectionMethod,
)
from app.modules.mapping.domain.value_objects import CreateServicePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalRule,
    CanonicalRuleAction,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalService,
    CanonicalServiceKind,
)
from app.modules.mapping.services.mapping_objects.mapping_objects_service import (
    MappingObjectsService,
)
from app.modules.mapping.services.mapping_rules.mapping_scope_rules_builder import (
    MappingScopeRulesBuilder,
)


def _canonical_service(
    *, kind: CanonicalServiceKind, protocol: str, port: int
) -> CanonicalService:
    return CanonicalService(
        id=uuid4(),
        kind=kind,
        name=f"{protocol}:{port}-{port}",
        protocol=protocol,
        port_from=port,
        port_to=port,
    )


def _service_operand(*, rule_id: UUID, service_id: UUID) -> CanonicalRuleOperand:
    return CanonicalRuleOperand(
        id=uuid4(),
        rule_id=rule_id,
        role=CanonicalRuleOperandRole.SERVICE,
        target_zone_id=None,
        target_object_id=service_id,
    )


@dataclass(slots=True)
class _CanonicalServiceReader:
    services_by_id: dict[UUID, CanonicalService]

    async def get_canonical_service(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalService | None:
        return self.services_by_id.get(canonical_object_id)


@dataclass(slots=True)
class _CreatingServiceGateway:
    payloads: list[CreateServicePayload] = field(default_factory=list)
    services: list[SdwanService] = field(default_factory=list)

    async def create_service(self, payload: CreateServicePayload) -> SdwanService:
        self.payloads.append(payload)
        service = SdwanService(
            id=900 + len(self.payloads),
            name=payload.name,
            l4_proto=payload.l4_proto,
            ranges=((payload.port_start, payload.port_end),),  # type: ignore[arg-type]
            codes=None,
        )
        self.services.append(service)
        return service

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return SdwanFullCatalog(
            zones=[],
            services=self.services,
            addr_objs=[],
            networks=[],
        )


@dataclass(slots=True)
class _CreatingServiceGatewayProvider:
    gateway: _CreatingServiceGateway
    acquire_calls: list[tuple[UUID, str]] = field(default_factory=list)

    @asynccontextmanager
    async def acquire(
        self, profile_id: UUID, vpc_id: str
    ) -> AsyncIterator[_CreatingServiceGateway]:
        self.acquire_calls.append((profile_id, vpc_id))
        yield self.gateway


def test_tcp_udp_leaves_map_independently_and_stay_separated_by_rule() -> None:
    tcp_53 = _canonical_service(kind=CanonicalServiceKind.TCP, protocol="tcp", port=53)
    tcp_5060 = _canonical_service(
        kind=CanonicalServiceKind.TCP, protocol="tcp", port=5060
    )
    udp_53 = _canonical_service(kind=CanonicalServiceKind.UDP, protocol="udp", port=53)
    udp_5060 = _canonical_service(
        kind=CanonicalServiceKind.UDP, protocol="udp", port=5060
    )
    canonical_entities = CanonicalScopeEntities(
        zones=[],
        addr_objects=[],
        services=[tcp_53, tcp_5060, udp_53, udp_5060],
    )
    sdwan_services = [
        SdwanService(
            id=101,
            name="TCP DNS",
            l4_proto=SdwanServiceL4Proto.TCP,
            ranges=((53, 53),),
            codes=None,
        ),
        SdwanService(
            id=102,
            name="TCP SIP",
            l4_proto=SdwanServiceL4Proto.TCP,
            ranges=((5060, 5060),),
            codes=None,
        ),
        SdwanService(
            id=201,
            name="UDP DNS",
            l4_proto=SdwanServiceL4Proto.UDP,
            ranges=((53, 53),),
            codes=None,
        ),
        SdwanService(
            id=202,
            name="UDP SIP",
            l4_proto=SdwanServiceL4Proto.UDP,
            ranges=((5060, 5060),),
            codes=None,
        ),
    ]
    mapping_scope_id = uuid4()
    mapping_results = MappingObjectsService.build_results(
        mapping_scope_id=mapping_scope_id,
        canonical_scope_entities=canonical_entities,
        sdwan_full_catalog=SdwanFullCatalog(
            zones=[],
            addr_objs=[],
            services=sdwan_services,
            networks=[],
        ),
    )

    assert len(mapping_results) == 4
    assert all(
        result.result_status == MappingResultStatus.MATCHED
        for result in mapping_results
    )
    selected_id_by_canonical_id = {
        result.canonical_entity_id: result.selected_sdwan_entity_id
        for result in mapping_results
    }
    assert selected_id_by_canonical_id == {
        tcp_53.id: 101,
        tcp_5060.id: 102,
        udp_53.id: 201,
        udp_5060.id: 202,
    }

    canonical_snapshot_id = uuid4()
    tcp_rule_id = uuid4()
    udp_rule_id = uuid4()
    canonical_rules = [
        CanonicalRule(
            id=tcp_rule_id,
            canonical_snapshot_id=canonical_snapshot_id,
            name="ACL:tcp",
            action=CanonicalRuleAction.PERMIT,
            priority=10,
            operands=[
                _service_operand(rule_id=tcp_rule_id, service_id=tcp_53.id),
                _service_operand(rule_id=tcp_rule_id, service_id=tcp_5060.id),
            ],
        ),
        CanonicalRule(
            id=udp_rule_id,
            canonical_snapshot_id=canonical_snapshot_id,
            name="ACL:udp",
            action=CanonicalRuleAction.PERMIT,
            priority=20,
            operands=[
                _service_operand(rule_id=udp_rule_id, service_id=udp_53.id),
                _service_operand(rule_id=udp_rule_id, service_id=udp_5060.id),
            ],
        ),
    ]
    mapped_rules = MappingScopeRulesBuilder().build(
        mapping_scope_id=mapping_scope_id,
        canonical_rules=canonical_rules,
        canonical_scope_entities=canonical_entities,
        mapping_results=mapping_results,
    )
    mapping_results_by_id = {result.id: result for result in mapping_results}

    selected_ids_by_rule_name = {
        rule.name: [
            mapping_results_by_id[
                operand.mapping_entity_result_id
            ].selected_sdwan_entity_id
            for operand in rule.operands or []
            if operand.role == MappingScopeRuleOperandRole.SERVICE
        ]
        for rule in mapped_rules
    }
    assert selected_ids_by_rule_name == {
        "ACL:tcp": [101, 102],
        "ACL:udp": [201, 202],
    }


@pytest.mark.asyncio
async def test_missing_tcp_udp_leaves_are_created_and_selected_independently() -> None:
    tcp_53 = _canonical_service(kind=CanonicalServiceKind.TCP, protocol="tcp", port=53)
    tcp_5060 = _canonical_service(
        kind=CanonicalServiceKind.TCP, protocol="tcp", port=5060
    )
    udp_53 = _canonical_service(kind=CanonicalServiceKind.UDP, protocol="udp", port=53)
    udp_5060 = _canonical_service(
        kind=CanonicalServiceKind.UDP, protocol="udp", port=5060
    )
    canonical_services = [tcp_53, tcp_5060, udp_53, udp_5060]
    initial_catalog = SdwanFullCatalog(
        zones=[],
        addr_objs=[],
        services=[
            SdwanService(
                id=101,
                name="TCP DNS",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((53, 53),),
                codes=None,
            ),
            SdwanService(
                id=201,
                name="UDP DNS",
                l4_proto=SdwanServiceL4Proto.UDP,
                ranges=((53, 53),),
                codes=None,
            ),
        ],
        networks=[],
    )
    mapping_scope = MappingScope.create_header(
        title="tcp-udp partial catalog",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="device-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint=initial_catalog.get_fingerprint(),
    )
    mapping_results = MappingObjectsService.build_results(
        mapping_scope_id=mapping_scope.id,
        canonical_scope_entities=CanonicalScopeEntities(
            zones=[],
            addr_objects=[],
            services=canonical_services,
        ),
        sdwan_full_catalog=initial_catalog,
    )
    results_by_canonical_id = {
        result.canonical_entity_id: result for result in mapping_results
    }

    assert (
        results_by_canonical_id[tcp_53.id].result_status == MappingResultStatus.MATCHED
    )
    assert (
        results_by_canonical_id[udp_53.id].result_status == MappingResultStatus.MATCHED
    )
    assert (
        results_by_canonical_id[tcp_5060.id].result_status
        == MappingResultStatus.UNRESOLVED
    )
    assert (
        results_by_canonical_id[udp_5060.id].result_status
        == MappingResultStatus.UNRESOLVED
    )

    mapping_repo = RuntimeCacheMappingRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=10)
    )
    await mapping_repo.add_scope(mapping_scope)
    await mapping_repo.add_results(mapping_scope.id, mapping_results)
    gateway = _CreatingServiceGateway(services=list(initial_catalog.services))
    gateway_provider = _CreatingServiceGatewayProvider(gateway)
    use_case = SelectEntityWithCreateOnSdwanUseCase(
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=gateway_provider,  # type: ignore[arg-type]
        canonical_reader=_CanonicalServiceReader(  # type: ignore[arg-type]
            {service.id: service for service in canonical_services}
        ),
        refresh_mapping_scope_catalog_fingerprint=(
            RefreshMappingScopeCatalogFingerprintUseCase(
                mapping_repo=mapping_repo,
                sdwan_gateway_provider=gateway_provider,  # type: ignore[arg-type]
            )
        ),
    )

    for service in (tcp_5060, udp_5060):
        await use_case.execute(
            SelectEntityWithCreateOnSdwanCommand(
                mapping_scope_id=mapping_scope.id,
                mapping_result_id=results_by_canonical_id[service.id].id,
            )
        )

    assert gateway.payloads == [
        CreateServicePayload(
            name="tcp:5060-5060",
            l4_proto=SdwanServiceL4Proto.TCP,
            port_start=5060,
            port_end=5060,
        ),
        CreateServicePayload(
            name="udp:5060-5060",
            l4_proto=SdwanServiceL4Proto.UDP,
            port_start=5060,
            port_end=5060,
        ),
    ]
    saved_results = await mapping_repo.list_results(scope_id=mapping_scope.id)
    assert all(
        result.result_status == MappingResultStatus.MATCHED for result in saved_results
    )
    created_results = [
        result
        for result in saved_results
        if result.selection_method == SdwanObjectSelectionMethod.AUTO_CREATED
    ]
    assert {
        result.canonical_entity_id: result.selected_sdwan_entity_id
        for result in created_results
    } == {
        tcp_5060.id: 901,
        udp_5060.id: 902,
    }
