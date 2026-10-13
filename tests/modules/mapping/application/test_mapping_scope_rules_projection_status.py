from uuid import uuid4

import pytest

from app.modules.mapping.application.dto import (
    CanonicalToSdwanEntityProjectionDTO,
    MappedSdwanEntityDisplayDTO,
)
from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    _MappingScopeRulesProjectionBuilder,
)
from app.modules.mapping.domain.enums import (
    MappedRuleStatus,
    MappingResultStatus,
    SdwanObjectSelectionMethod,
)

_ROLE_NAMES = (
    "src_zones",
    "dst_zones",
    "src_addr_objects",
    "dst_addr_objects",
    "services",
)


def _row(
    status: MappingResultStatus = MappingResultStatus.MATCHED,
    *,
    sdwan_id: int | None = 1,
) -> CanonicalToSdwanEntityProjectionDTO:
    return CanonicalToSdwanEntityProjectionDTO(
        canonical=None,
        sdwan=MappedSdwanEntityDisplayDTO(
            mapping_result_id=uuid4(),
            match_status=status,
            selection_method=(
                SdwanObjectSelectionMethod.AUTO_SELECTED
                if status == MappingResultStatus.MATCHED
                else None
            ),
            sdwan_id=sdwan_id,
            name="entity" if sdwan_id is not None else None,
            type="test" if sdwan_id is not None else None,
            str_value=None,
        ),
    )


def _status(
    overrides: dict[str, list[CanonicalToSdwanEntityProjectionDTO]] | None = None,
) -> MappedRuleStatus:
    roles = {role: [_row()] for role in _ROLE_NAMES}
    roles.update(overrides or {})
    return _MappingScopeRulesProjectionBuilder._aggregate_rule_status_by_roles(
        **roles,
    )


def test_rule_is_mapped_when_every_required_role_contains_only_matched_objects() -> (
    None
):
    assert _status() == MappedRuleStatus.MAPPED


@pytest.mark.parametrize("missing_role", _ROLE_NAMES)
def test_rule_is_partial_when_required_role_is_empty(missing_role: str) -> None:
    assert _status({missing_role: []}) == MappedRuleStatus.PARTIAL


def test_rule_is_partial_when_any_object_in_role_is_unresolved() -> None:
    assert (
        _status(
            {
                "services": [
                    _row(),
                    _row(MappingResultStatus.UNRESOLVED, sdwan_id=None),
                ]
            }
        )
        == MappedRuleStatus.PARTIAL
    )


def test_rule_is_ambiguous_when_any_object_in_role_is_ambiguous() -> None:
    assert (
        _status(
            {
                "services": [
                    _row(),
                    _row(MappingResultStatus.AMBIGUOUS, sdwan_id=None),
                ]
            }
        )
        == MappedRuleStatus.AMBIGUOUS
    )


def test_matched_object_without_selected_sdwan_id_is_not_ready() -> None:
    assert (
        _status({"services": [_row(MappingResultStatus.MATCHED, sdwan_id=None)]})
        == MappedRuleStatus.PARTIAL
    )


def test_rule_is_unresolved_when_all_required_roles_are_empty() -> None:
    assert (
        _status({role: [] for role in _ROLE_NAMES})
        == MappedRuleStatus.UNRESOLVED
    )
