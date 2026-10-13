from uuid import uuid4

import pytest

from app.modules.mapping.domain.entities import (
    MappingEntityCandidate,
    MappingEntityResult,
)
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingResultStatus,
    SdwanObjectSelectionMethod,
)
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload


def _candidate_payload(sdwan_entity_id: int) -> MappingEntityCandidatePayload:
    return MappingEntityCandidatePayload(
        rank=1,
        score=100,
        strategy=CandidateMatchStrategy.EXACT_VALUE,
        sdwan_entity_id=sdwan_entity_id,
    )


@pytest.mark.parametrize(
    "entity_type",
    [
        MappingEntityType.ZONE,
        MappingEntityType.ADDR,
        MappingEntityType.SERVICE,
    ],
)
def test_create_unresolved_keeps_canonical_link_for_entity_type(
    entity_type: MappingEntityType,
) -> None:
    canonical_entity_id = uuid4()

    result = MappingEntityResult.create_unresolved(
        mapping_scope_id=uuid4(),
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
    )

    assert result.canonical_entity_id == canonical_entity_id
    assert result.result_status == MappingResultStatus.UNRESOLVED
    assert result.selection_method is None
    assert result.selected_sdwan_entity_id is None
    assert result.candidates == []
    assert (result.canonical_zone_id is not None) == (
        entity_type == MappingEntityType.ZONE
    )


def test_ambiguous_result_selects_its_candidate_without_losing_candidates() -> None:
    result = MappingEntityResult.create_ambiguous(
        mapping_scope_id=uuid4(),
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
        candidates_payloads=[_candidate_payload(10), _candidate_payload(20)],
    )
    candidate = (result.candidates or [])[1]

    selected = result.select_candidate(candidate)

    assert result.result_status == MappingResultStatus.AMBIGUOUS
    assert selected.result_status == MappingResultStatus.MATCHED
    assert selected.selection_method == SdwanObjectSelectionMethod.MANUAL_CANDIDATE
    assert selected.selected_sdwan_entity_id == 20
    assert selected.candidates == result.candidates


def test_select_candidate_rejects_candidate_from_another_result() -> None:
    result = MappingEntityResult.create_ambiguous(
        mapping_scope_id=uuid4(),
        entity_type=MappingEntityType.SERVICE,
        canonical_entity_id=uuid4(),
        candidates_payloads=[_candidate_payload(443), _candidate_payload(8443)],
    )
    foreign_candidate = MappingEntityCandidate.create(
        result_id=uuid4(),
        rank=1,
        score=100,
        strategy=CandidateMatchStrategy.SERVICE_SIGNATURE,
        sdwan_entity_id=443,
    )

    with pytest.raises(ValueError, match="does not belong"):
        result.select_candidate(foreign_candidate)


@pytest.mark.parametrize(
    ("method", "expected_selection_method"),
    [
        ("select_direct", SdwanObjectSelectionMethod.MANUAL_DIRECT),
        ("select_created", SdwanObjectSelectionMethod.AUTO_CREATED),
    ],
)
def test_selected_result_records_selection_method(
    method: str,
    expected_selection_method: SdwanObjectSelectionMethod,
) -> None:
    result = MappingEntityResult.create_unresolved(
        mapping_scope_id=uuid4(),
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
    )

    selected = getattr(result, method)(101)

    assert selected.result_status == MappingResultStatus.MATCHED
    assert selected.selection_method == expected_selection_method
    assert selected.selected_sdwan_entity_id == 101


def test_manual_zone_has_no_canonical_entity() -> None:
    result = MappingEntityResult.create_zone_manually_assigned(
        mapping_scope_id=uuid4(),
        sdwan_zone_id=7,
    )

    assert result.result_status == MappingResultStatus.MATCHED
    assert result.selection_method == SdwanObjectSelectionMethod.MANUAL_DIRECT
    assert result.selected_sdwan_entity_id == 7
    with pytest.raises(ValueError, match="ZONE have no canonical_zone_id"):
        _ = result.canonical_entity_id
