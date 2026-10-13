from uuid import uuid4

from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import (
    CoverageField,
    RuleMatchStatus,
    SdwanRuleAction,
)
from app.modules.execute.domain.value_objects import (
    CoverageDetail,
    CoverageValue,
    PlannedRuleDraft,
)
from streamlit_app.components.execute.coverage_details import (
    build_coverage_detail_rows,
)


def _plan_rule(*, coverage_details: tuple[CoverageDetail, ...]) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=uuid4(),
        mapping_scope_rule_id=uuid4(),
        priority=0,
        draft=PlannedRuleDraft(
            name="global_access:3",
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[30],
        ),
        matched_sdwan_rule_id=9,
        match_status=RuleMatchStatus.COVERED_MATCH,
        match_info="Found cover sdwan rule 9 for planned rule",
        coverage_details=coverage_details,
    )


def test_build_coverage_detail_rows_groups_values_under_covering_object() -> None:
    plan_rule = _plan_rule(
        coverage_details=(
            CoverageDetail(
                field=CoverageField.SRC_ADDR_OBJECTS,
                covering_value=CoverageValue(
                    object_id=1,
                    object_name="any-source",
                    value="0.0.0.0-255.255.255.255",
                ),
                covered_values=(
                    CoverageValue(2, "source-a", "172.31.64.0-172.31.71.255"),
                    CoverageValue(3, "source-b", "172.31.128.0-172.31.135.255"),
                ),
            ),
        )
    )

    rows = build_coverage_detail_rows(plan_rule)

    assert len(rows) == 1
    assert rows[0].field == "Source addresses"
    assert rows[0].covered_by_existing_object == (
        "any-source (0.0.0.0-255.255.255.255)"
    )
    assert (
        rows[0].covered_planned_objects
        == "source-a (172.31.64.0-172.31.71.255)\nsource-b (172.31.128.0-172.31.135.255)"
    )


def test_build_coverage_detail_rows_returns_nothing_without_strict_details() -> None:
    assert build_coverage_detail_rows(_plan_rule(coverage_details=())) == []
