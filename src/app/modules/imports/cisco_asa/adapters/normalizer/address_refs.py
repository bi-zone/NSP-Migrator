from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.modules.canonical.domain import CanonicalObject, ObjectFamily, ObjectKind
from app.modules.imports.cisco_asa.adapters.normalizer.state import (
    _mask_to_prefix,
    _NormalizerState,
    _ObjectRef,
)
from app.modules.imports.cisco_asa.domain.enums import IssueReasonCode
from app.modules.trace.domain.enums import TraceCanonicalKind


def ensure_host_ref(
    *,
    ref: str,
    source_line: int,
    role: str,
    state: _NormalizerState,
) -> UUID:
    """Resolve ACL host: ref into canonical object id, creating object on demand.

    This path is used for rule operands and therefore emits trace records to keep
    line-level provenance.
    """
    ip = ref.removeprefix("host:")
    key = f"addr:host:{ip}"
    if key not in state.objects_by_key:
        obj = CanonicalObject.create(
            canonical_snapshot_id=state.canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.HOST,
            name=ip,
            ip_version=4,
            cidr=f"{ip}/32",
        )
        state.register(obj)
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=obj.id,
            source_fragment=f"host {ip}",
            canonical_role=role,
            note="inline host materialized from ACL operand",
        )
    return state.objects_by_key[key].object_id


def ensure_subnet_ref(
    *,
    ref: str,
    source_line: int,
    role: str,
    state: _NormalizerState,
) -> UUID:
    """Resolve ACL net: ref into canonical object id, creating object on demand.

    Invalid subnet masks are represented as unresolved address objects so
    downstream mapping cannot widen them to addr:any.
    """
    body = ref.removeprefix("net:")
    ip_str, mask = body.split("/", 1)
    prefix = _mask_to_prefix(mask)
    if prefix is None:
        return ensure_unresolved_ref(
            ref=ref,
            source_line=source_line,
            role=role,
            state=state,
        )
    cidr = f"{ip_str}/{prefix}"
    key = f"addr:net:{cidr}"
    if key not in state.objects_by_key:
        obj = CanonicalObject.create(
            canonical_snapshot_id=state.canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.SUBNET,
            name=cidr,
            ip_version=4,
            cidr=cidr,
        )
        state.register(obj)
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=obj.id,
            source_fragment=cidr,
            canonical_role=role,
            note="inline subnet materialized from ACL operand",
        )
    return state.objects_by_key[key].object_id


def ensure_unresolved_ref(
    *,
    ref: str,
    source_line: int,
    role: str,
    state: _NormalizerState,
) -> UUID:
    """Create/reuse unresolved address fallback object and emit issue + trace.

    This helper is used when a named address reference cannot be mapped to an
    existing object key.
    """
    unresolved_key = f"addr:unresolved:{ref}"
    if unresolved_key in state.objects_by_key:
        return state.objects_by_key[unresolved_key].object_id

    fallback = CanonicalObject.create(
        canonical_snapshot_id=state.canonical_snapshot_id,
        object_key=unresolved_key,
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.UNRESOLVED_ADDR,
        name=ref,
        description="unresolved ASA address reference",
    )
    state.register(fallback)
    state.emit_trace(
        line_start=source_line,
        line_end=source_line,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=fallback.id,
        source_fragment=ref,
        canonical_role=role,
        note="unresolved address reference fallback",
    )
    state.emit_issue(
        entity_type="cisco_asa_rule",
        issue_code="unresolved_address_ref",
        message=f"Unresolved ASA address reference: {ref}",
        entity_key=ref,
        source_line_start=source_line,
        source_line_end=source_line,
        source_fragment=ref,
        reason=IssueReasonCode.MAPPING_MISSING,
    )
    return fallback.id


def resolve_host_member(
    *,
    ref: str,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str:
    """Resolve address-group host: member to object key.

    Unlike ensure_* helpers, resolve_* helpers return keys and do not emit
    traces/issues directly. Group-level helpers decide how to trace/report.
    """
    ip = ref.removeprefix("host:")
    key = f"addr:host:{ip}"
    if key not in objects_by_key:
        obj = CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.HOST,
            name=ip,
            ip_version=4,
            cidr=f"{ip}/32",
        )
        register(obj)
    return key


def resolve_subnet_member(
    *,
    ref: str,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str | None:
    """Resolve address-group net: member to object key or None on bad mask."""
    body = ref.removeprefix("net:")
    ip_str, mask = body.split("/", 1)
    prefix = _mask_to_prefix(mask)
    if prefix is None:
        return None
    cidr = f"{ip_str}/{prefix}"
    key = f"addr:net:{cidr}"
    if key not in objects_by_key:
        obj = CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.SUBNET,
            name=cidr,
            ip_version=4,
            cidr=cidr,
        )
        register(obj)
    return key


def resolve_unresolved_member(
    *,
    ref: str,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str:
    """Create/reuse an unresolved address leaf for a group member."""
    key = f"addr:unresolved:{ref}"
    if key not in objects_by_key:
        register(
            CanonicalObject.create(
                canonical_snapshot_id=canonical_snapshot_id,
                object_key=key,
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.UNRESOLVED_ADDR,
                name=ref,
                description="unresolved ASA address group member",
            )
        )
    return key


def resolve_member_ref(
    ref: str,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str | None:
    """Resolve address-group member reference into canonical object key.

    Returns:
        Resolved key for host/subnet/named object, or None when unresolved.
    """
    if ref.startswith("host:"):
        return resolve_host_member(
            ref=ref,
            canonical_snapshot_id=canonical_snapshot_id,
            objects_by_key=objects_by_key,
            register=register,
        )

    if ref.startswith("net:"):
        resolved_key = resolve_subnet_member(
            ref=ref,
            canonical_snapshot_id=canonical_snapshot_id,
            objects_by_key=objects_by_key,
            register=register,
        )
        return resolved_key or resolve_unresolved_member(
            ref=ref,
            canonical_snapshot_id=canonical_snapshot_id,
            objects_by_key=objects_by_key,
            register=register,
        )

    named_key = f"addr:{ref}"
    if named_key in objects_by_key:
        return named_key
    return resolve_unresolved_member(
        ref=ref,
        canonical_snapshot_id=canonical_snapshot_id,
        objects_by_key=objects_by_key,
        register=register,
    )
