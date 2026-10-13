from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeCommand,
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateCommand,
    SelectEntityCandidateUseCase,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyCommand,
    SelectSdwanEntityDirectlyUseCase,
)
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
    MappingScopeRulesPriority,
    SDWANZoneDirection,
    SdwanObjectSelectionMethod,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.domain.value_objects import (
    MappingEntityCandidatePayload,
    MappingScopeRuleOperandPayload,
)


def _scope(*, rules: list[MappingScopeRule] | None = None) -> MappingScope:
    scope = MappingScope.create_header(
        title="scope",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint="catalog",
    )
    return scope.attach_rules(rules or [])


def _rule(scope_id: UUID) -> MappingScopeRule:
    return MappingScopeRule.create(
        mapping_scope_id=scope_id,
        canonical_rule_id=uuid4(),
        name="rule",
        action=MappingScopeRuleAction.ACCEPT,
        priority=0,
        operands_payloads=[],
    )


@dataclass
class _MappingRepositoryFake:
    scope: MappingScope | None = None
    result: MappingEntityResult | None = None
    saved_result: MappingEntityResult | None = None
    added_results: list[MappingEntityResult] = field(default_factory=list)
    added_operands: list[MappingScopeRuleOperand] = field(default_factory=list)

    async def get_scope_by_id(
        self, scope_id: UUID, *, with_rules: bool = False
    ) -> MappingScope | None:
        if self.scope is None or self.scope.id != scope_id:
            return None
        return self.scope

    async def get_result(
        self,
        scope_id: UUID,
        result_id: UUID,
        *,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        if (
            self.result is None
            or self.result.mapping_scope_id != scope_id
            or self.result.id != result_id
        ):
            return None
        return self.result

    async def save_result(self, result: MappingEntityResult) -> MappingEntityResult:
        self.saved_result = result
        self.result = result
        return result

    async def add_results(
        self, *, scope_id: UUID, results: list[MappingEntityResult]
    ) -> None:
        assert self.scope is not None and scope_id == self.scope.id
        self.added_results.extend(results)

    async def list_results(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType | None = None,
        status: MappingResultStatus | None = None,
        with_candidates: bool = False,
    ) -> list[MappingEntityResult]:
        assert self.scope is not None and scope_id == self.scope.id
        results = [*self.added_results]
        if self.result is not None:
            results.append(self.result)
        return [
            result
            for result in results
            if (entity_type is None or result.entity_type == entity_type)
            and (status is None or result.result_status == status)
        ]

    async def add_rule_operand(
        self, *, scope_id: UUID, operand: MappingScopeRuleOperand
    ) -> None:
        assert self.scope is not None and scope_id == self.scope.id
        self.added_operands.append(operand)
        rules = self.scope.rules or []
        self.scope = self.scope.attach_rules(
            [
                replace(
                    rule,
                    operands=[*(rule.operands or []), operand],
                )
                if rule.id == operand.mapping_scope_rule_id
                else rule
                for rule in rules
            ]
        )


@dataclass
class _GatewayFake:
    zone: SdwanZone | None = None
    service: SdwanService | None = None
    address: SdwanAddrObject | None = None

    async def get_zone(self, entity_id: int) -> SdwanZone | None:
        return (
            self.zone if self.zone is not None and self.zone.id == entity_id else None
        )

    async def get_service(self, entity_id: int) -> SdwanService | None:
        return (
            self.service
            if self.service is not None and self.service.id == entity_id
            else None
        )

    async def get_addr_object(self, entity_id: int) -> SdwanAddrObject | None:
        return (
            self.address
            if self.address is not None and self.address.id == entity_id
            else None
        )


@dataclass
class _GatewayProviderFake:
    gateway: _GatewayFake
    acquisitions: list[tuple[UUID, str]] = field(default_factory=list)

    @asynccontextmanager
    async def acquire(
        self, profile_id: UUID, vpc_id: str
    ) -> AsyncIterator[_GatewayFake]:
        self.acquisitions.append((profile_id, vpc_id))
        yield self.gateway


def _ambiguous_result(scope_id: UUID) -> MappingEntityResult:
    return MappingEntityResult.create_ambiguous(
        mapping_scope_id=scope_id,
        entity_type=MappingEntityType.SERVICE,
        canonical_entity_id=uuid4(),
        candidates_payloads=[
            MappingEntityCandidatePayload(
                rank=1,
                score=100,
                strategy=CandidateMatchStrategy.SERVICE_SIGNATURE,
                sdwan_entity_id=443,
            ),
            MappingEntityCandidatePayload(
                rank=2,
                score=90,
                strategy=CandidateMatchStrategy.SERVICE_SIGNATURE,
                sdwan_entity_id=8443,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_select_candidate_persists_selected_mapping_state() -> None:
    scope = _scope()
    result = _ambiguous_result(scope.id)
    repository = _MappingRepositoryFake(scope=scope, result=result)
    selected_candidate = (result.candidates or [])[1]

    selected = await SelectEntityCandidateUseCase(repository).execute(
        SelectEntityCandidateCommand(
            mapping_scope_id=scope.id,
            mapping_entity_result_id=result.id,
            candidate_id=selected_candidate.id,
        )
    )

    assert selected.mapping_entity_result == repository.saved_result
    assert selected.mapping_entity_result.result_status == MappingResultStatus.MATCHED
    assert (
        selected.mapping_entity_result.selection_method
        == SdwanObjectSelectionMethod.MANUAL_CANDIDATE
    )
    assert selected.mapping_entity_result.selected_sdwan_entity_id == 8443


@pytest.mark.asyncio
async def test_select_candidate_rejects_candidate_not_linked_to_result() -> None:
    scope = _scope()
    result = _ambiguous_result(scope.id)
    repository = _MappingRepositoryFake(scope=scope, result=result)

    with pytest.raises(MappingModuleDomainValidationError, match="not linked"):
        await SelectEntityCandidateUseCase(repository).execute(
            SelectEntityCandidateCommand(
                mapping_scope_id=scope.id,
                mapping_entity_result_id=result.id,
                candidate_id=uuid4(),
            )
        )


def _sdwan_entity_fixture(
    entity_type: MappingEntityType,
) -> tuple[int, _GatewayFake]:
    if entity_type == MappingEntityType.ZONE:
        return 1, _GatewayFake(
            zone=SdwanZone(id=1, zone_id=101, name="LAN", type=SdwanZoneType.LAN)
        )
    if entity_type == MappingEntityType.SERVICE:
        return 100, _GatewayFake(
            service=SdwanService(
                id=100,
                name="https",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((443, 443),),
                codes=None,
            )
        )
    return 10, _GatewayFake(
        address=SdwanAddrObject(
            id=10,
            parents=(),
            name="host",
            type=SdwanAddrObjectType.HOST,
            host=IPv4Address("192.0.2.10"),
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    [MappingEntityType.ZONE, MappingEntityType.SERVICE, MappingEntityType.ADDR],
)
async def test_direct_selection_validates_matching_entity_type_and_persists_result(
    entity_type: MappingEntityType,
) -> None:
    scope = _scope()
    entity_id, gateway = _sdwan_entity_fixture(entity_type)
    result = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=entity_type,
        canonical_entity_id=uuid4(),
    )
    repository = _MappingRepositoryFake(scope=scope, result=result)
    provider = _GatewayProviderFake(gateway)

    selected = await SelectSdwanEntityDirectlyUseCase(repository, provider).execute(
        SelectSdwanEntityDirectlyCommand(
            mapping_scope_id=scope.id,
            mapping_result_id=result.id,
            sdwan_entity_id=entity_id,
        )
    )

    assert selected.mapping_result == repository.saved_result
    assert selected.mapping_result.selected_sdwan_entity_id == entity_id
    assert (
        selected.mapping_result.selection_method
        == SdwanObjectSelectionMethod.MANUAL_DIRECT
    )
    assert provider.acquisitions == [(scope.csp_profile_id, scope.vpc_id)]


@pytest.mark.asyncio
async def test_direct_selection_rejects_unknown_sdwan_entity() -> None:
    scope = _scope()
    result = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.ZONE,
        canonical_entity_id=uuid4(),
    )

    with pytest.raises(MappingModuleNotFoundError, match="not found"):
        await SelectSdwanEntityDirectlyUseCase(
            _MappingRepositoryFake(scope=scope, result=result),
            _GatewayProviderFake(_GatewayFake()),
        ).execute(
            SelectSdwanEntityDirectlyCommand(
                mapping_scope_id=scope.id,
                mapping_result_id=result.id,
                sdwan_entity_id=999,
            )
        )


@pytest.mark.asyncio
async def test_assign_zone_adds_manual_mapping_operand_to_every_scope_rule() -> None:
    scope_header = _scope()
    scope = scope_header.attach_rules([_rule(scope_header.id), _rule(scope_header.id)])
    repository = _MappingRepositoryFake(scope=scope)
    zone = SdwanZone(id=7, zone_id=107, name="WAN", type=SdwanZoneType.WAN)
    provider = _GatewayProviderFake(_GatewayFake(zone=zone))

    assigned = await AssignZoneForScopeUseCase(repository, provider).execute(
        AssignZoneForScopeCommand(
            mapping_scope_id=scope.id,
            zone_sdwan_id=zone.id,
            zone_direction=SDWANZoneDirection.DST_ZONE,
        )
    )

    assert assigned.mapping_result in repository.added_results
    assert assigned.mapping_result.canonical_zone_id is None
    assert assigned.mapping_result.selected_sdwan_entity_id == zone.id
    assert len(assigned.operands) == 2
    assert all(
        operand.role == MappingScopeRuleOperandRole.DST_ZONE
        and operand.mapping_entity_result_id == assigned.mapping_result.id
        for operand in assigned.operands
    )
    assert repository.added_operands == assigned.operands


@pytest.mark.asyncio
async def test_assign_zone_is_idempotent_for_same_zone_and_direction() -> None:
    scope_header = _scope()
    scope = scope_header.attach_rules([_rule(scope_header.id), _rule(scope_header.id)])
    repository = _MappingRepositoryFake(scope=scope)
    zone = SdwanZone(id=7, zone_id=107, name="WAN", type=SdwanZoneType.WAN)
    use_case = AssignZoneForScopeUseCase(
        repository,
        _GatewayProviderFake(_GatewayFake(zone=zone)),
    )
    command = AssignZoneForScopeCommand(
        mapping_scope_id=scope.id,
        zone_sdwan_id=zone.id,
        zone_direction=SDWANZoneDirection.DST_ZONE,
    )

    first_assignment = await use_case.execute(command)
    repeated_assignment = await use_case.execute(command)

    assert repeated_assignment.mapping_result == first_assignment.mapping_result
    assert repeated_assignment.operands == []
    assert repository.added_results == [first_assignment.mapping_result]
    assert repository.added_operands == first_assignment.operands


@pytest.mark.asyncio
async def test_assign_zone_adds_only_to_rules_missing_zone_in_selected_direction() -> (
    None
):
    scope_header = _scope()
    existing_zone_result = MappingEntityResult.create_zone_manually_assigned(
        mapping_scope_id=scope_header.id,
        sdwan_zone_id=7,
    )
    first_rule = _rule(scope_header.id)
    first_rule_with_zone = replace(
        first_rule,
        operands=[
            MappingScopeRuleOperand.create(
                mapping_scope_rule_id=first_rule.id,
                payload=MappingScopeRuleOperandPayload(
                    role=MappingScopeRuleOperandRole.DST_ZONE,
                    mapping_entity_result_id=existing_zone_result.id,
                ),
            )
        ],
    )
    scope = scope_header.attach_rules([first_rule_with_zone, _rule(scope_header.id)])
    repository = _MappingRepositoryFake(scope=scope, result=existing_zone_result)
    zone = SdwanZone(id=7, zone_id=107, name="WAN", type=SdwanZoneType.WAN)

    assignment = await AssignZoneForScopeUseCase(
        repository,
        _GatewayProviderFake(_GatewayFake(zone=zone)),
    ).execute(
        AssignZoneForScopeCommand(
            mapping_scope_id=scope.id,
            zone_sdwan_id=zone.id,
            zone_direction=SDWANZoneDirection.DST_ZONE,
        )
    )

    assert assignment.mapping_result == existing_zone_result
    assert repository.added_results == []
    assert [operand.mapping_scope_rule_id for operand in assignment.operands] == [
        scope.rules[1].id
    ]


@pytest.mark.asyncio
async def test_assign_zone_is_noop_when_rule_has_matching_canonical_zone() -> None:
    scope_header = _scope()
    canonical_zone_result = MappingEntityResult.create_matched_auto(
        mapping_scope_id=scope_header.id,
        entity_type=MappingEntityType.ZONE,
        canonical_entity_id=uuid4(),
        candidate_payload=MappingEntityCandidatePayload(
            rank=1,
            score=100,
            strategy=CandidateMatchStrategy.EXACT_VALUE,
            sdwan_entity_id=7,
        ),
    )
    rule = _rule(scope_header.id)
    scope = scope_header.attach_rules(
        [
            replace(
                rule,
                operands=[
                    MappingScopeRuleOperand.create(
                        mapping_scope_rule_id=rule.id,
                        payload=MappingScopeRuleOperandPayload(
                            role=MappingScopeRuleOperandRole.DST_ZONE,
                            mapping_entity_result_id=canonical_zone_result.id,
                        ),
                    )
                ],
            )
        ]
    )
    repository = _MappingRepositoryFake(scope=scope, result=canonical_zone_result)
    zone = SdwanZone(id=7, zone_id=107, name="WAN", type=SdwanZoneType.WAN)

    assignment = await AssignZoneForScopeUseCase(
        repository,
        _GatewayProviderFake(_GatewayFake(zone=zone)),
    ).execute(
        AssignZoneForScopeCommand(
            mapping_scope_id=scope.id,
            zone_sdwan_id=zone.id,
            zone_direction=SDWANZoneDirection.DST_ZONE,
        )
    )

    assert assignment.mapping_result == canonical_zone_result
    assert assignment.operands == []
    assert repository.added_results == []
    assert repository.added_operands == []


@pytest.mark.asyncio
async def test_assign_zone_does_not_treat_other_direction_as_already_assigned() -> None:
    scope_header = _scope()
    scope = scope_header.attach_rules([_rule(scope_header.id)])
    repository = _MappingRepositoryFake(scope=scope)
    zone = SdwanZone(id=7, zone_id=107, name="WAN", type=SdwanZoneType.WAN)
    use_case = AssignZoneForScopeUseCase(
        repository,
        _GatewayProviderFake(_GatewayFake(zone=zone)),
    )

    destination_assignment = await use_case.execute(
        AssignZoneForScopeCommand(
            mapping_scope_id=scope.id,
            zone_sdwan_id=zone.id,
            zone_direction=SDWANZoneDirection.DST_ZONE,
        )
    )
    source_assignment = await use_case.execute(
        AssignZoneForScopeCommand(
            mapping_scope_id=scope.id,
            zone_sdwan_id=zone.id,
            zone_direction=SDWANZoneDirection.SRC_ZONE,
        )
    )

    assert source_assignment.mapping_result == destination_assignment.mapping_result
    assert len(source_assignment.operands) == 1
    assert source_assignment.operands[0].role == MappingScopeRuleOperandRole.SRC_ZONE
    assert repository.added_results == [destination_assignment.mapping_result]


@pytest.mark.asyncio
async def test_assign_zone_requires_existing_scope_rules() -> None:
    scope = _scope()

    with pytest.raises(MappingModuleNotFoundError, match="Not provided rules"):
        await AssignZoneForScopeUseCase(
            _MappingRepositoryFake(scope=scope),
            _GatewayProviderFake(_GatewayFake()),
        ).execute(
            AssignZoneForScopeCommand(
                mapping_scope_id=scope.id,
                zone_sdwan_id=7,
                zone_direction=SDWANZoneDirection.SRC_ZONE,
            )
        )
