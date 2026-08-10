from __future__ import annotations

from uuid import UUID

from app.modules.canonical.domain import CanonicalObjectMember
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.domain.enums import IssueReasonCode
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


def emit_materialized_member_objects(
    *,
    source_line: int,
    member: dict,
    keys_before: set[str],
    state: _NormalizerState,
) -> None:
    """Emit traces for service objects materialized during one member step.

    The caller passes keys_before captured right before
    materialize_service_group_member runs. Only keys added to
    state.objects_by_key in that step receive object traces (e.g. inline
    port-object, icmp-object, or parsed service-object children).

    Side Effects:
        Appends TraceCanonicalKind.OBJECT records to state.trace_records.
    """
    for new_key in state.objects_by_key.keys() - keys_before:
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=state.objects_by_key[new_key].object_id,
            source_fragment=str(member),
            note="service group member materialized",
        )


def emit_unresolved_member_issue(
    *,
    group_name: str,
    member: dict,
    source_line: int,
    entity_type: str,
    state: _NormalizerState,
) -> None:
    """Emit issue when a group member could not be resolved to child object keys.

    Invoked from _attach_group_members when materialize_service_group_member
    returns an empty child_keys list. entity_type distinguishes caller
    context:

    - cisco_asa_service_group from _materialize_service_group_members
    - cisco_asa_protocol_group from _materialize_protocol_group_members

    Side Effects:
        Appends a CanonicalIssue via state.emit_issue.

    Stable contracts:
        issue_code=unresolved_group_member_ref is asserted in
        tests/imports/cisco_asa/test_trace_fixtures.py and fixture docs.
    """
    state.emit_issue(
        entity_type=entity_type,
        issue_code="unresolved_group_member_ref",
        message=f"Unresolved service group member in {group_name}: {member}",
        entity_key=f"{group_name}:{member.get('type')}",
        source_line_start=source_line,
        source_line_end=source_line,
        source_fragment=str(member),
        reason=IssueReasonCode.MAPPING_MISSING,
    )


def attach_group_member_edges(
    *,
    parent_id: UUID,
    child_keys: list[str],
    pos: int,
    source_line: int,
    member: dict,
    state: _NormalizerState,
) -> None:
    """Append parent->child membership edges for one parsed group member.

    Called after successful member resolution in _attach_group_members.
    A single member may yield multiple child_keys; edge positions use
    pos + offset so expanded members preserve stable ordering within the
    group body.

    Missing keys are skipped silently — resolution is assumed to have already
    decided whether the member is valid.

    Side Effects:
        Appends CanonicalObjectMember rows and OBJECT_MEMBER traces.
    """
    for offset, child_key in enumerate(child_keys):
        if child_key not in state.objects_by_key:
            continue
        edge = CanonicalObjectMember.create(
            parent_object_id=parent_id,
            child_object_id=state.objects_by_key[child_key].object_id,
            position=pos if offset == 0 else pos + offset,
        )
        state.object_members.append(edge)
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT_MEMBER,
            canonical_id=edge.id,
            source_fragment=str(member),
            canonical_role=TraceCanonicalRole.MEMBER_REF.value,
        )