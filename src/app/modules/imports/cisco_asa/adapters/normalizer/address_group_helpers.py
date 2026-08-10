from __future__ import annotations

from uuid import UUID

from app.modules.canonical.domain import CanonicalObjectMember
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.domain.enums import IssueReasonCode
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


def emit_materialized_address_member_objects(
    *,
    source_line: int,
    member_ref: object,
    keys_before: set[str],
    state: _NormalizerState,
) -> None:
    """Emit traces for address objects materialized during current member step.

    The caller passes keys_before captured right before member resolution.
    The function compares it with current state.objects_by_key to detect
    only newly created objects and append trace records for that delta.

    Side Effects:
        Appends TraceCanonicalKind.OBJECT records to state.trace_records.
    """
    for new_key in state.objects_by_key.keys() - keys_before:
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=state.objects_by_key[new_key].object_id,
            source_fragment=str(member_ref),
            note="inline member materialized from group body",
        )


def attach_address_group_member_edge(
    *,
    parent_id: UUID,
    child_object_id: UUID,
    position: int,
    source_line: int,
    member_ref: object,
    state: _NormalizerState,
) -> None:
    """Attach one parent->child membership edge for an address group member.

    Side Effects:
        - Appends a CanonicalObjectMember to state.object_members.
        - Appends a corresponding TraceCanonicalKind.OBJECT_MEMBER record.
    """
    member = CanonicalObjectMember.create(
        parent_object_id=parent_id,
        child_object_id=child_object_id,
        position=position,
    )
    state.object_members.append(member)
    state.emit_trace(
        line_start=source_line,
        line_end=source_line,
        canonical_kind=TraceCanonicalKind.OBJECT_MEMBER,
        canonical_id=member.id,
        source_fragment=str(member_ref),
        canonical_role=TraceCanonicalRole.MEMBER_REF.value,
    )


def emit_unresolved_address_group_member_issue(
    *,
    group_name: str,
    member_ref: str,
    source_line: int,
    state: _NormalizerState,
) -> None:
    """Emit domain issue for unresolved address-group member reference.

    The issue_code is intentionally stable because tests and downstream
    analytics rely on this taxonomy for regression detection and reporting.

    Side Effects:
        Appends a CanonicalIssue and related trace record via
        state.emit_issue(...).
    """
    state.emit_issue(
        entity_type="cisco_asa_address_group",
        issue_code="unresolved_group_member_ref",
        message=f"Unresolved address group member reference: {group_name} -> {member_ref}",
        entity_key=f"{group_name}:{member_ref}",
        source_line_start=source_line,
        source_line_end=source_line,
        source_fragment=member_ref,
        reason=IssueReasonCode.MAPPING_MISSING,
    )