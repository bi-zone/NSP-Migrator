"""Integration tests for canonical rule filters, sorting, and scope projection."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.core.querying import Pagination, SortDirection, Sorting
from app.modules.canonical.adapters.db.uow import CanonicalUoW
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesQuery,
    GetCanonicalRulesUseCase,
)
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleSearchScope,
    CanonicalRuleSortField,
)
from tests.modules.canonical.conftest import CanonicalScenario


async def _get_rules(
    *,
    uow_factory: Callable[[], CanonicalUoW],
    scenario: CanonicalScenario,
    filters: CanonicalRuleFilters | None = None,
    pagination: Pagination | None = None,
    sorting: Sorting[CanonicalRuleSortField] | None = None,
):
    return await GetCanonicalRulesUseCase(uow_factory()).execute(
        GetCanonicalRulesQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            filters=filters or CanonicalRuleFilters(),
            pagination=pagination or Pagination(),
            sorting=sorting,
        )
    )


def _keys(result) -> list[str]:
    return [rule.rule_key for rule in result.rules]


@pytest.mark.asyncio
async def test_exact_and_operand_filters_are_applied_with_and_semantics(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Cover ID, scalar, zone, direct object, and nested object filters."""
    scenario: CanonicalScenario = await canonical_scenario_factory()
    expected = {
        "nested": [scenario.rules["nested"].rule_key],
        "blocked": [scenario.rules["blocked"].rule_key],
        "admin": [scenario.rules["admin"].rule_key],
    }
    cases = [
        (
            CanonicalRuleFilters(rule_ids=[scenario.rules["admin"].id]),
            expected["admin"],
        ),
        (CanonicalRuleFilters(action="deny"), expected["blocked"]),
        (CanonicalRuleFilters(enabled=False), expected["blocked"]),
        (CanonicalRuleFilters(section="outside_in"), expected["nested"]),
        (
            CanonicalRuleFilters(operand_zone_ids=[scenario.zones["dmz"].id]),
            expected["blocked"],
        ),
        (
            CanonicalRuleFilters(operand_object_ids=[scenario.objects["fqdn"].id]),
            expected["blocked"],
        ),
        (
            CanonicalRuleFilters(
                operand_object_ids=[scenario.objects["payroll_host"].id]
            ),
            expected["nested"],
        ),
        (
            CanonicalRuleFilters(
                action="permit",
                enabled=True,
                section="outside_in",
                operand_zone_ids=[scenario.zones["outside"].id],
                operand_object_ids=[scenario.objects["payroll_host"].id],
            ),
            expected["nested"],
        ),
        (
            CanonicalRuleFilters(action="deny", enabled=True),
            [],
        ),
    ]

    for filters, expected_keys in cases:
        result = await _get_rules(
            uow_factory=canonical_uow_factory,
            scenario=scenario,
            filters=filters,
        )
        assert _keys(result) == expected_keys
        assert result.pagination.total == len(expected_keys)


@pytest.mark.asyncio
async def test_scoped_search_matches_rule_zone_and_nested_object_fields(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Verify case-insensitive search scopes and zero-hit scope isolation."""
    scenario: CanonicalScenario = await canonical_scenario_factory()
    cases = [
        ("  ORCHID  ", CanonicalRuleSearchScope.RULES, "admin"),
        ("payroll", CanonicalRuleSearchScope.OBJECTS, "nested"),
        ("10.20.30.40", CanonicalRuleSearchScope.OBJECTS, "nested"),
        ("blocked-primary.example", CanonicalRuleSearchScope.OBJECTS, "blocked"),
        ("PERIMETER", CanonicalRuleSearchScope.ZONES, "nested"),
        ("dns primary", CanonicalRuleSearchScope.ALL, "blocked"),
    ]

    for search, scope, expected_rule in cases:
        result = await _get_rules(
            uow_factory=canonical_uow_factory,
            scenario=scenario,
            filters=CanonicalRuleFilters(search=search, search_scope=scope),
        )
        assert _keys(result) == [scenario.rules[expected_rule].rule_key]
        assert result.pagination.total == 1

    wrong_scope = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=scenario,
        filters=CanonicalRuleFilters(
            search="10.20.30.40",
            search_scope=CanonicalRuleSearchScope.RULES,
        ),
    )
    missing_object = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=scenario,
        filters=CanonicalRuleFilters(
            search="does-not-exist",
            search_scope=CanonicalRuleSearchScope.OBJECTS,
        ),
    )
    assert wrong_scope.rules == []
    assert wrong_scope.pagination.total == 0
    assert missing_object.rules == []
    assert missing_object.pagination.total == 0


@pytest.mark.asyncio
async def test_pagination_count_sorting_and_page_operands_stay_consistent(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Keep total unpaged, use deterministic ordering, and hydrate only the page."""
    scenario: CanonicalScenario = await canonical_scenario_factory()

    default_page = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=scenario,
        pagination=Pagination(limit=1, offset=1),
    )
    assert _keys(default_page) == [scenario.rules["admin"].rule_key]
    assert default_page.pagination.limit == 1
    assert default_page.pagination.offset == 1
    assert default_page.pagination.total == 3
    assert len(default_page.rules[0].operands or []) == 3

    sorted_result = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=scenario,
        sorting=Sorting(
            field=CanonicalRuleSortField.NAME,
            direction=SortDirection.DESC,
        ),
    )
    assert _keys(sorted_result) == [
        scenario.rules["admin"].rule_key,
        scenario.rules["blocked"].rule_key,
        scenario.rules["nested"].rule_key,
    ]


@pytest.mark.asyncio
async def test_internal_fw_applicable_filter_and_snapshot_isolation(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Cover mapping-only metadata filtering and reject cross-snapshot rule IDs."""
    first: CanonicalScenario = await canonical_scenario_factory(label="first")
    second: CanonicalScenario = await canonical_scenario_factory(label="second")

    applicable = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=first,
        filters=CanonicalRuleFilters(fw_applicable_only=True),
    )
    skipped = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=first,
        filters=CanonicalRuleFilters(fw_applicable_only=False),
    )
    foreign_id = await _get_rules(
        uow_factory=canonical_uow_factory,
        scenario=first,
        filters=CanonicalRuleFilters(rule_ids=[second.rules["nested"].id]),
    )

    assert set(_keys(applicable)) == {
        first.rules["nested"].rule_key,
        first.rules["admin"].rule_key,
    }
    assert _keys(skipped) == [first.rules["blocked"].rule_key]
    assert foreign_id.rules == []
    assert foreign_id.pagination.total == 0


@pytest.mark.asyncio
async def test_rule_scope_narrows_references_and_expands_nested_groups(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Return only matched-rule references while retaining transitive members."""
    scenario: CanonicalScenario = await canonical_scenario_factory()
    use_case = GetCanonicalRuleScopeUseCase(canonical_uow_factory())
    result = await use_case.execute(
        GetCanonicalRuleScopeQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            filters=CanonicalRuleFilters(rule_ids=[scenario.rules["nested"].id]),
        )
    )

    assert [rule.id for rule in result.rules] == [scenario.rules["nested"].id]
    assert result.pagination.total == 1
    assert {zone.id for zone in result.zones} == {
        scenario.zones["outside"].id,
        scenario.zones["inside"].id,
    }
    objects = {obj.id: obj for obj in result.objects}
    assert set(objects) == {
        scenario.objects["outer_group"].id,
        scenario.objects["inner_group"].id,
        scenario.objects["payroll_host"].id,
        scenario.objects["http"].id,
    }
    assert objects[scenario.objects["inner_group"].id].parent_ids == (
        scenario.objects["outer_group"].id,
    )
    assert objects[scenario.objects["payroll_host"].id].parent_ids == (
        scenario.objects["inner_group"].id,
    )

    all_zones = await GetCanonicalRuleScopeUseCase(canonical_uow_factory()).execute(
        GetCanonicalRuleScopeQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            filters=CanonicalRuleFilters(rule_ids=[scenario.rules["nested"].id]),
            include_all_zones=True,
        )
    )
    assert {zone.id for zone in all_zones.zones} == {
        zone.id for zone in scenario.zones.values()
    }


@pytest.mark.asyncio
async def test_unfiltered_rule_scope_returns_complete_snapshot_catalogs(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Keep mapping's unfiltered contract including unused zones and objects."""
    scenario: CanonicalScenario = await canonical_scenario_factory()
    result = await GetCanonicalRuleScopeUseCase(canonical_uow_factory()).execute(
        GetCanonicalRuleScopeQuery(canonical_snapshot_id=scenario.snapshot_id)
    )

    assert len(result.rules) == len(scenario.rules)
    assert len(result.zones) == len(scenario.zones)
    assert len(result.objects) == len(scenario.objects)
    assert result.pagination.total == len(scenario.rules)
