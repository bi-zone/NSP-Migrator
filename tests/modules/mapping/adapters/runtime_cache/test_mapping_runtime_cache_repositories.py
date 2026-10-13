from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.infrastructure.cache import InMemoryTTLStore
from app.modules.mapping.adapters.runtime_cache import RuntimeCacheMappingRepository
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
)
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload


def _scope(scope_id: UUID | None = None, *, created_at: datetime | None = None):
    return MappingScope(
        id=scope_id or uuid4(),
        title="scope",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint="catalog-fingerprint",
        created_at=created_at or datetime.now(UTC),
        rules=None,
    )


def _rule(scope_id: UUID, *, priority: int = 0) -> MappingScopeRule:
    return MappingScopeRule.create(
        mapping_scope_id=scope_id,
        canonical_rule_id=uuid4(),
        name="rule",
        action=MappingScopeRuleAction.ACCEPT,
        priority=priority,
        operands_payloads=[],
    )


def _repository() -> RuntimeCacheMappingRepository:
    return RuntimeCacheMappingRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=100)
    )


@pytest.mark.asyncio
async def test_scope_repository_stores_scope_header_and_rules() -> None:
    repository = _repository()
    scope = _scope()
    rule = _rule(scope.id)

    await repository.add_scope(scope)
    await repository.attach_rules(scope_id=scope.id, rules=[rule])

    loaded_scope = await repository.get_scope_by_id(scope.id)
    with_rules = await repository.get_scope_by_id(
        scope.id,
        with_rules=True,
    )

    assert loaded_scope is not None
    assert loaded_scope.rules == [rule]
    assert with_rules is not None
    assert with_rules.rules == [rule]


@pytest.mark.asyncio
async def test_scope_repository_sorts_rules_by_priority_stably() -> None:
    repository = _repository()
    scope = _scope()
    later_rule = _rule(scope.id, priority=20)
    first_same_priority_rule = _rule(scope.id, priority=10)
    second_same_priority_rule = _rule(scope.id, priority=10)

    await repository.add_scope(scope)
    await repository.attach_rules(
        scope_id=scope.id,
        rules=[later_rule, first_same_priority_rule, second_same_priority_rule],
    )

    loaded_scope = await repository.get_scope_by_id(scope.id, with_rules=True)

    assert loaded_scope is not None
    assert loaded_scope.rules == [
        first_same_priority_rule,
        second_same_priority_rule,
        later_rule,
    ]


@pytest.mark.asyncio
async def test_scope_repository_refreshes_catalog_fingerprint() -> None:
    repository = _repository()
    scope = _scope()

    await repository.add_scope(scope)
    refreshed = await repository.refresh_catalog_fingerprint(
        scope_id=scope.id,
        catalog_fingerprint="new-catalog-fingerprint",
    )

    assert refreshed.catalog_fingerprint == "new-catalog-fingerprint"


@pytest.mark.asyncio
async def test_scope_repository_adds_rule_operand() -> None:
    repository = _repository()
    scope = _scope()
    rule = _rule(scope.id)
    operand = MappingScopeRuleOperand(
        id=uuid4(),
        mapping_scope_rule_id=rule.id,
        role=MappingScopeRuleOperandRole.SERVICE,
        mapping_entity_result_id=uuid4(),
    )

    await repository.add_scope(scope)
    await repository.attach_rules(scope_id=scope.id, rules=[rule])
    await repository.add_rule_operand(
        scope_id=scope.id,
        operand=operand,
    )

    stored_scope = await repository.get_scope_by_id(
        scope.id,
        with_rules=True,
    )

    assert stored_scope is not None
    assert stored_scope.rules is not None
    assert stored_scope.rules[0].operands == [operand]


@pytest.mark.asyncio
async def test_scope_repository_lists_recent_scopes_without_rules() -> None:
    repository = _repository()
    older = _scope(created_at=datetime.now(UTC) - timedelta(hours=1))
    newer = _scope(created_at=datetime.now(UTC))
    rule = _rule(older.id)

    await repository.add_scope(older)
    await repository.add_scope(newer)
    await repository.attach_rules(scope_id=older.id, rules=[rule])

    scopes = await repository.list_recent_scopes()

    assert [scope.id for scope in scopes] == [newer.id, older.id]
    assert scopes[0].rules == []
    assert scopes[1].rules == [rule]


@pytest.mark.asyncio
async def test_result_repository_stores_and_filters_results() -> None:
    repository = _repository()
    scope = _scope()
    zone_entity_id = uuid4()
    addr_entity_id = uuid4()
    zone_result = _matched_result(
        scope_id=scope.id,
        entity_type=MappingEntityType.ZONE,
        canonical_entity_id=zone_entity_id,
        sdwan_entity_id=10,
    )
    addr_result = _unresolved_result(
        scope_id=scope.id,
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=addr_entity_id,
    )

    await repository.add_scope(scope)
    await repository.add_results(
        scope_id=scope.id,
        results=[zone_result, addr_result],
    )

    by_id = await repository.get_result(
        scope_id=scope.id,
        result_id=zone_result.id,
    )
    by_canonical = await repository.find_result_by_canonical_entity(
        scope_id=scope.id,
        entity_type=MappingEntityType.ZONE,
        canonical_entity_id=zone_entity_id,
    )
    unresolved = await repository.list_results(
        scope_id=scope.id,
        status=MappingResultStatus.UNRESOLVED,
    )

    assert by_id == zone_result
    assert by_canonical == zone_result
    assert unresolved == [addr_result]


@pytest.mark.asyncio
async def test_result_repository_preserves_candidates_when_saving_partial_result() -> (
    None
):
    repository = _repository()
    scope = _scope()
    canonical_entity_id = uuid4()
    result = _ambiguous_result(
        scope_id=scope.id,
        canonical_entity_id=canonical_entity_id,
    )

    await repository.add_scope(scope)
    await repository.add_results(
        scope_id=scope.id,
        results=[result],
    )

    loaded_without_candidates = await repository.get_result(
        scope_id=scope.id,
        result_id=result.id,
    )
    assert loaded_without_candidates is not None
    saved = loaded_without_candidates.select_direct(42)
    await repository.save_result(saved)

    loaded_with_candidates = await repository.get_result(
        scope_id=scope.id,
        result_id=result.id,
        with_candidates=True,
    )

    assert loaded_with_candidates is not None
    assert loaded_with_candidates.candidates == result.candidates
    assert loaded_with_candidates.selected_sdwan_entity_id == 42


def _matched_result(
    *,
    scope_id: UUID,
    entity_type: MappingEntityType,
    canonical_entity_id: UUID,
    sdwan_entity_id: int,
):
    result = _ambiguous_result(
        scope_id=scope_id,
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
    )
    candidate = next(
        item
        for item in result.candidates or []
        if item.sdwan_entity_id == sdwan_entity_id
    )
    return result.select_candidate(candidate)


def _ambiguous_result(
    *,
    scope_id: UUID,
    canonical_entity_id: UUID,
    entity_type: MappingEntityType = MappingEntityType.SERVICE,
):
    return MappingEntityResult.create_ambiguous(
        mapping_scope_id=scope_id,
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
        candidates_payloads=[
            MappingEntityCandidatePayload(
                rank=1,
                score=100,
                strategy=CandidateMatchStrategy.NORMALIZED_NAME,
                sdwan_entity_id=10,
            ),
            MappingEntityCandidatePayload(
                rank=2,
                score=80,
                strategy=CandidateMatchStrategy.EXACT_VALUE,
                sdwan_entity_id=20,
            ),
        ],
    )


def _unresolved_result(
    *,
    scope_id: UUID,
    entity_type: MappingEntityType,
    canonical_entity_id: UUID,
):
    return MappingEntityResult.create_unresolved(
        mapping_scope_id=scope_id,
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
    )
