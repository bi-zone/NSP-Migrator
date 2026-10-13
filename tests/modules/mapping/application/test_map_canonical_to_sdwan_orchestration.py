from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanDeviceObjectType,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
    SdwanZone,
)
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
    MapCanonicalToSdwanUseCase,
)
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
)
from app.modules.mapping.domain.enums import (
    MappingResultStatus,
    MappingScopeRulesPriority,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalRule,
    CanonicalRuleAction,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalZone,
)


@dataclass
class _MappingRepositoryFake:
    scope: MappingScope | None = None
    results: list[MappingEntityResult] = field(default_factory=list)
    rules: list[MappingScopeRule] = field(default_factory=list)

    async def add_scope(self, scope: MappingScope) -> MappingScope:
        self.scope = scope
        return scope

    async def add_results(
        self, *, scope_id: UUID, results: list[MappingEntityResult]
    ) -> None:
        assert self.scope is not None and scope_id == self.scope.id
        self.results = results

    async def attach_rules(
        self, *, scope_id: UUID, rules: list[MappingScopeRule]
    ) -> None:
        assert self.scope is not None and scope_id == self.scope.id
        self.rules = rules


@dataclass
class _GatewayFake:
    target: SdwanDeviceObject | None
    catalog: SdwanFullCatalog

    async def get_device_object(self, *, dev_obj_id: str) -> SdwanDeviceObject | None:
        if self.target is None or self.target.dev_obj_id != dev_obj_id:
            return None
        return self.target

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return self.catalog


@dataclass
class _GatewayProviderFake:
    gateway: _GatewayFake

    @asynccontextmanager
    async def acquire(
        self, profile_id: UUID, vpc_id: str
    ) -> AsyncIterator[_GatewayFake]:
        yield self.gateway


@dataclass
class _CanonicalReaderFake:
    entities: CanonicalScopeEntities
    rules: list[CanonicalRule]
    requested_rule_ids: list[UUID] | None = None

    async def get_canonical_scope_entities_data(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> CanonicalScopeEntities:
        self.requested_rule_ids = canonical_rules_ids
        return self.entities

    async def get_canonical_scope_rules(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> list[CanonicalRule]:
        assert canonical_rules_ids == self.requested_rule_ids
        return self.rules


def _command(*, priority: MappingScopeRulesPriority) -> MapCanonicalToSdwanCommand:
    return MapCanonicalToSdwanCommand(
        mapping_scope_title="Migration",
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=priority,
        canonical_snapshot_id=uuid4(),
        canonical_rules_ids=[uuid4()],
    )


def _target(target_type: SdwanDeviceObjectType) -> SdwanDeviceObject:
    return SdwanDeviceObject(
        dev_obj_id="target-1",
        name="Target",
        type=target_type,
        cpe_id=("cpe-1" if target_type == SdwanDeviceObjectType.DEVICE else None),
    )


@pytest.mark.asyncio
async def test_map_canonical_to_sdwan_persists_built_scope_results_and_rules() -> None:
    command = _command(priority=MappingScopeRulesPriority.LOCAL)
    zone = CanonicalZone(id=uuid4(), zone_key="inside", name="Inside")
    canonical_rule = CanonicalRule(
        id=command.canonical_rules_ids[0],
        canonical_snapshot_id=command.canonical_snapshot_id,
        name="Allow",
        action=CanonicalRuleAction.PERMIT,
        priority=10,
        operands=[
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=command.canonical_rules_ids[0],
                role=CanonicalRuleOperandRole.SRC_ZONE,
                target_zone_id=zone.id,
                target_object_id=None,
            )
        ],
    )
    repository = _MappingRepositoryFake()
    reader = _CanonicalReaderFake(
        entities=CanonicalScopeEntities(zones=[zone], addr_objects=[], services=[]),
        rules=[canonical_rule],
    )
    catalog = SdwanFullCatalog(
        zones=[SdwanZone(id=1, zone_id=101, name="inside", type=SdwanZoneType.LAN)],
        services=[],
        addr_objs=[],
        networks=[],
    )

    result = await MapCanonicalToSdwanUseCase(
        mapping_repo=repository,
        sdwan_gateway_provider=_GatewayProviderFake(
            _GatewayFake(_target(SdwanDeviceObjectType.DEVICE), catalog)
        ),  # type: ignore[arg-type]
        canonical_reader=reader,  # type: ignore[arg-type]
    ).execute(command)

    assert repository.scope is not None
    assert result.mapping_scope_id == repository.scope.id
    assert repository.scope.catalog_fingerprint == catalog.get_fingerprint()
    assert reader.requested_rule_ids == command.canonical_rules_ids
    assert result.mapping_results_summary.matched_entities == 1
    assert repository.results[0].result_status == MappingResultStatus.MATCHED
    assert result.mapped_rules_count == 1
    assert repository.rules[0].operands is not None
    assert (
        repository.rules[0].operands[0].mapping_entity_result_id
        == repository.results[0].id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_type", "priority"),
    [
        (SdwanDeviceObjectType.DEVICE, MappingScopeRulesPriority.PRE),
        (SdwanDeviceObjectType.GROUP, MappingScopeRulesPriority.LOCAL),
    ],
)
async def test_map_canonical_to_sdwan_rejects_priority_not_supported_by_target(
    target_type: SdwanDeviceObjectType,
    priority: MappingScopeRulesPriority,
) -> None:
    command = _command(priority=priority)
    catalog = SdwanFullCatalog(zones=[], services=[], addr_objs=[], networks=[])

    with pytest.raises(MappingModuleDomainValidationError, match="Policies"):
        await MapCanonicalToSdwanUseCase(
            mapping_repo=_MappingRepositoryFake(),  # type: ignore[arg-type]
            sdwan_gateway_provider=_GatewayProviderFake(
                _GatewayFake(_target(target_type), catalog)
            ),  # type: ignore[arg-type]
            canonical_reader=_CanonicalReaderFake(
                entities=CanonicalScopeEntities([], [], []), rules=[]
            ),  # type: ignore[arg-type]
        ).execute(command)


@pytest.mark.asyncio
async def test_map_canonical_to_sdwan_requires_existing_target_and_rule_ids() -> None:
    catalog = SdwanFullCatalog(zones=[], services=[], addr_objs=[], networks=[])
    absent_target_command = _command(priority=MappingScopeRulesPriority.LOCAL)
    no_target_use_case = MapCanonicalToSdwanUseCase(
        mapping_repo=_MappingRepositoryFake(),  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderFake(_GatewayFake(None, catalog)),  # type: ignore[arg-type]
        canonical_reader=_CanonicalReaderFake(
            entities=CanonicalScopeEntities([], [], []), rules=[]
        ),  # type: ignore[arg-type]
    )
    with pytest.raises(MappingModuleNotFoundError, match="Target"):
        await no_target_use_case.execute(absent_target_command)

    no_rules_command = MapCanonicalToSdwanCommand(
        mapping_scope_title="Migration",
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        canonical_snapshot_id=uuid4(),
        canonical_rules_ids=[],
    )
    with pytest.raises(MappingModuleDomainValidationError, match="rules ids"):
        await MapCanonicalToSdwanUseCase(
            mapping_repo=_MappingRepositoryFake(),  # type: ignore[arg-type]
            sdwan_gateway_provider=_GatewayProviderFake(
                _GatewayFake(_target(SdwanDeviceObjectType.DEVICE), catalog)
            ),  # type: ignore[arg-type]
            canonical_reader=_CanonicalReaderFake(
                entities=CanonicalScopeEntities([], [], []), rules=[]
            ),  # type: ignore[arg-type]
        ).execute(no_rules_command)
