from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.modules.execute.adapters.mapping_reader import MappingReader
from app.modules.execute.errors import ExecuteModuleError
from app.modules.mapping.application.get_mapping_scope import GetMappingScopeResult
from app.modules.mapping.application.get_mapping_scope_rules import (
    GetMappingScopeRulesResult,
)
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
)
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
    MappingScopeRulesPriority,
)
from app.modules.mapping.domain.value_objects import (
    MappingEntityCandidatePayload,
    MappingScopeRuleOperandPayload,
)

_ROLES = (
    MappingScopeRuleOperandRole.SRC_ZONE,
    MappingScopeRuleOperandRole.DST_ZONE,
    MappingScopeRuleOperandRole.SRC_ADDR_OBJECT,
    MappingScopeRuleOperandRole.DST_ADDR_OBJECT,
    MappingScopeRuleOperandRole.SERVICE,
)


@dataclass(slots=True)
class _GetMappedRulesStub:
    result: GetMappingScopeRulesResult

    async def execute(self, query: object) -> GetMappingScopeRulesResult:
        return self.result


@dataclass(slots=True)
class _GetMappingScopeStub:
    result: GetMappingScopeResult

    async def execute(self, query: object) -> GetMappingScopeResult:
        return self.result


def _entity_type(role: MappingScopeRuleOperandRole) -> MappingEntityType:
    if role in (
        MappingScopeRuleOperandRole.SRC_ZONE,
        MappingScopeRuleOperandRole.DST_ZONE,
    ):
        return MappingEntityType.ZONE
    if role == MappingScopeRuleOperandRole.SERVICE:
        return MappingEntityType.SERVICE
    return MappingEntityType.ADDR


def _mapped_rule_fixture(
    *,
    missing_role: MappingScopeRuleOperandRole | None = None,
) -> tuple[UUID, MappingScopeRule, list[MappingEntityResult]]:
    mapping_scope_id = uuid4()
    results_by_role: dict[MappingScopeRuleOperandRole, MappingEntityResult] = {}

    for sdwan_id, role in enumerate(_ROLES, start=1):
        results_by_role[role] = MappingEntityResult.create_matched_auto(
            mapping_scope_id=mapping_scope_id,
            entity_type=_entity_type(role),
            canonical_entity_id=uuid4(),
            candidate_payload=MappingEntityCandidatePayload(
                rank=1,
                score=100,
                strategy=CandidateMatchStrategy.EXACT_VALUE,
                sdwan_entity_id=sdwan_id,
            ),
        )

    rule = MappingScopeRule.create(
        mapping_scope_id=mapping_scope_id,
        canonical_rule_id=uuid4(),
        name="rule",
        action=MappingScopeRuleAction.ACCEPT,
        priority=10,
        operands_payloads=[
            MappingScopeRuleOperandPayload(
                role=role,
                mapping_entity_result_id=result.id,
            )
            for role, result in results_by_role.items()
            if role != missing_role
        ],
    )
    return mapping_scope_id, rule, list(results_by_role.values())


def _reader(
    rule: MappingScopeRule,
    mapping_results: list[MappingEntityResult],
) -> MappingReader:
    return MappingReader(
        get_mapped_rules=_GetMappedRulesStub(  # type: ignore
            GetMappingScopeRulesResult(
                rules=[rule],
                mapping_results=mapping_results,
            )
        ),
        get_mapping_scope=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_mapping_reader_returns_rule_when_all_roles_are_complete() -> None:
    mapping_scope_id, rule, results = _mapped_rule_fixture()

    mapped_rules = await _reader(rule, results).get_mapping_scope_rules(
        mapping_scope_id
    )

    assert len(mapped_rules) == 1
    assert mapped_rules[0].name == "rule"
    assert mapped_rules[0].priority == 10
    assert mapped_rules[0].src_zones
    assert mapped_rules[0].dst_zones
    assert mapped_rules[0].src_addr_objects
    assert mapped_rules[0].dst_addr_objects
    assert mapped_rules[0].services


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_role", _ROLES)
async def test_mapping_reader_rejects_every_missing_required_role(
    missing_role: MappingScopeRuleOperandRole,
) -> None:
    mapping_scope_id, rule, results = _mapped_rule_fixture(missing_role=missing_role)

    with pytest.raises(ExecuteModuleError, match=missing_role.value):
        await _reader(rule, results).get_mapping_scope_rules(mapping_scope_id)


def _matched_result(
    *,
    mapping_scope_id: UUID,
    entity_type: MappingEntityType,
    sdwan_id: int,
) -> MappingEntityResult:
    return MappingEntityResult.create_matched_auto(
        mapping_scope_id=mapping_scope_id,
        entity_type=entity_type,
        canonical_entity_id=uuid4(),
        candidate_payload=MappingEntityCandidatePayload(
            rank=1,
            score=100,
            strategy=CandidateMatchStrategy.SERVICE_SIGNATURE,
            sdwan_entity_id=sdwan_id,
        ),
    )


def _tcp_udp_rules_fixture(
    *, unresolved_udp_service: bool = False
) -> tuple[UUID, list[MappingScopeRule], list[MappingEntityResult]]:
    mapping_scope_id = uuid4()
    common_results = {
        role: _matched_result(
            mapping_scope_id=mapping_scope_id,
            entity_type=_entity_type(role),
            sdwan_id=sdwan_id,
        )
        for sdwan_id, role in enumerate(_ROLES[:-1], start=1)
    }
    tcp_results = [
        _matched_result(
            mapping_scope_id=mapping_scope_id,
            entity_type=MappingEntityType.SERVICE,
            sdwan_id=101,
        ),
        _matched_result(
            mapping_scope_id=mapping_scope_id,
            entity_type=MappingEntityType.SERVICE,
            sdwan_id=102,
        ),
    ]
    udp_results = [
        _matched_result(
            mapping_scope_id=mapping_scope_id,
            entity_type=MappingEntityType.SERVICE,
            sdwan_id=201,
        ),
        (
            MappingEntityResult.create_unresolved(
                mapping_scope_id=mapping_scope_id,
                entity_type=MappingEntityType.SERVICE,
                canonical_entity_id=uuid4(),
            )
            if unresolved_udp_service
            else _matched_result(
                mapping_scope_id=mapping_scope_id,
                entity_type=MappingEntityType.SERVICE,
                sdwan_id=202,
            )
        ),
    ]

    def build_rule(name: str, service_results: list[MappingEntityResult]):
        return MappingScopeRule.create(
            mapping_scope_id=mapping_scope_id,
            canonical_rule_id=uuid4(),
            name=name,
            action=MappingScopeRuleAction.ACCEPT,
            priority=0,
            operands_payloads=[
                *[
                    MappingScopeRuleOperandPayload(
                        role=role,
                        mapping_entity_result_id=result.id,
                    )
                    for role, result in common_results.items()
                ],
                *[
                    MappingScopeRuleOperandPayload(
                        role=MappingScopeRuleOperandRole.SERVICE,
                        mapping_entity_result_id=result.id,
                    )
                    for result in service_results
                ],
            ],
        )

    rules = [
        build_rule("tcp-rule", tcp_results),
        build_rule("udp-rule", udp_results),
    ]
    results = [*common_results.values(), *tcp_results, *udp_results]
    return mapping_scope_id, rules, results


@pytest.mark.asyncio
async def test_mapping_reader_keeps_all_tcp_udp_service_ids_separated_by_rule() -> None:
    mapping_scope_id, rules, results = _tcp_udp_rules_fixture()
    reader = MappingReader(
        get_mapped_rules=_GetMappedRulesStub(  # type: ignore[arg-type]
            GetMappingScopeRulesResult(rules=rules, mapping_results=results)
        ),
        get_mapping_scope=None,  # type: ignore[arg-type]
    )

    mapped_rules = await reader.get_mapping_scope_rules(mapping_scope_id)
    mapped_by_id = {rule.id: rule for rule in mapped_rules}

    assert mapped_by_id[rules[0].id].services == [101, 102]
    assert mapped_by_id[rules[1].id].services == [201, 202]


@pytest.mark.asyncio
async def test_mapping_reader_rejects_scope_with_unresolved_tcp_udp_leaf() -> None:
    mapping_scope_id, rules, results = _tcp_udp_rules_fixture(
        unresolved_udp_service=True
    )
    unresolved = next(
        result
        for result in results
        if result.result_status == MappingResultStatus.UNRESOLVED
    )
    assert unresolved.selected_sdwan_entity_id is None
    reader = MappingReader(
        get_mapped_rules=_GetMappedRulesStub(  # type: ignore[arg-type]
            GetMappingScopeRulesResult(rules=rules, mapping_results=results)
        ),
        get_mapping_scope=None,  # type: ignore[arg-type]
    )

    with pytest.raises(ExecuteModuleError, match="has unmatched objects"):
        await reader.get_mapping_scope_rules(mapping_scope_id)


@pytest.mark.asyncio
async def test_mapping_reader_preserves_scope_metadata_required_by_execute() -> None:
    scope = MappingScope.create_header(
        title="migration",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.POST,
        catalog_fingerprint="catalog-fingerprint",
    )
    reader = MappingReader(
        get_mapped_rules=None,  # type: ignore[arg-type]
        get_mapping_scope=_GetMappingScopeStub(GetMappingScopeResult(scope)),  # type: ignore[arg-type]
    )

    data = await reader.get_mapping_scope_data(scope.id)

    assert data.id == scope.id
    assert data.csp_profile_id == scope.csp_profile_id
    assert data.vpc_id == "vpc-1"
    assert data.sdwan_target_id == "target-1"
    assert data.rules_priority == MappingScopeRulesPriority.POST
    assert data.catalog_fingerprint == "catalog-fingerprint"
