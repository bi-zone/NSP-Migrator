import pytest

from app.modules.execute.domain.enums import SdwanRuleAction
from app.modules.execute.domain.value_objects import PlannedRuleDraft


def _payload(**overrides: object) -> dict[str, str | list[int]]:
    data: dict[str, str | list[int]] = {
        "name": "allow-web",
        "action": "ACCEPT",
        "src_zones": [1],
        "dst_zones": [2],
        "src_addr_objects": [10],
        "dst_addr_objects": [20],
        "services": [30],
    }
    data.update(overrides)
    return data


def test_planned_rule_draft_round_trip_preserves_semantic_fields() -> None:
    draft = PlannedRuleDraft.from_dict(_payload())

    assert draft == PlannedRuleDraft(
        name="allow-web",
        action=SdwanRuleAction.ACCEPT,
        src_zones=[1],
        dst_zones=[2],
        src_addr_objects=[10],
        dst_addr_objects=[20],
        services=[30],
    )
    assert draft.to_dict() == _payload()


def test_planned_rule_draft_restores_numeric_references_from_json_strings() -> None:
    draft = PlannedRuleDraft.from_dict(
        _payload(
            src_zones=["1"],  # type: ignore[dict-item]
            dst_addr_objects=["20"],  # type: ignore[dict-item]
        )
    )

    assert draft.src_zones == [1]
    assert draft.dst_addr_objects == [20]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("src_zones", "1"),
        ("dst_zones", {2}),
        ("src_addr_objects", None),
    ],
)
def test_planned_rule_draft_rejects_non_list_reference_collections(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="Expected list"):
        PlannedRuleDraft.from_dict(_payload(**{field: value}))  # type: ignore[arg-type]


def test_planned_rule_draft_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        PlannedRuleDraft.from_dict(_payload(action="ALLOW"))
