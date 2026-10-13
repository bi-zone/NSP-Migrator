"""Pure view-model helpers for the user-facing Trace inspector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode
from uuid import UUID

from app.modules.trace.domain.enums import TraceCanonicalKind


ROLE_LABELS = {
    "src_zone": "Source zone",
    "dst_zone": "Destination zone",
    "src_object": "Source",
    "dst_object": "Destination",
    "service": "Service",
    "header": "Definition",
    "member_ref": "Group member",
    "from_acl_name": "Derived from ACL name",
    "from_access_group_binding": "Derived from access-group binding",
}

KIND_LABELS = {
    "rule": "Rule",
    "object": "Object",
    "object_member": "Group member",
    "zone": "Zone",
    "rule_operand": "Rule field",
    "issue": "Problem",
}


@dataclass(frozen=True, slots=True)
class TraceDeepLink:
    """Validated entity filter restored from Trace URL query parameters."""

    source_snapshot_id: UUID
    canonical_snapshot_id: UUID
    canonical_kind: TraceCanonicalKind
    canonical_id: UUID


@dataclass(frozen=True, slots=True)
class CanonicalDeepLink:
    """Validated canonical entity context restored from URL query parameters."""

    source_snapshot_id: UUID
    canonical_snapshot_id: UUID
    canonical_kind: TraceCanonicalKind
    canonical_id: UUID
    context_rule_id: UUID | None = None


def build_trace_url(
    *,
    source_snapshot_id: str,
    canonical_snapshot_id: str,
    canonical_kind: str,
    canonical_id: str,
) -> str:
    """Build a shareable same-app URL for an isolated canonical entity trace."""
    query = urlencode(
        {
            "source_snapshot_id": source_snapshot_id,
            "canonical_snapshot_id": canonical_snapshot_id,
            "canonical_kind": canonical_kind,
            "canonical_id": canonical_id,
        }
    )
    return f"/trace-rules?{query}"


def build_canonical_url(
    *,
    source_snapshot_id: str,
    canonical_snapshot_id: str,
    canonical_kind: str,
    canonical_id: str,
    context_rule_id: str | None = None,
) -> str:
    """Build a Canonical page URL filtered to an entity or its rule context."""
    params = {
        "source_snapshot_id": source_snapshot_id,
        "canonical_snapshot_id": canonical_snapshot_id,
        "canonical_kind": canonical_kind,
        "canonical_id": canonical_id,
    }
    if context_rule_id:
        params["context_rule_id"] = context_rule_id
    return f"/canonical-rules?{urlencode(params)}"


def parse_trace_deep_link(params: Mapping[str, str]) -> TraceDeepLink | None:
    """Parse a complete entity deep-link, returning None for partial/invalid input."""
    required = (
        "source_snapshot_id",
        "canonical_snapshot_id",
        "canonical_kind",
        "canonical_id",
    )
    if not all(params.get(key) for key in required):
        return None
    try:
        return TraceDeepLink(
            source_snapshot_id=UUID(params["source_snapshot_id"]),
            canonical_snapshot_id=UUID(params["canonical_snapshot_id"]),
            canonical_kind=TraceCanonicalKind(params["canonical_kind"]),
            canonical_id=UUID(params["canonical_id"]),
        )
    except (ValueError, TypeError):
        return None


def parse_canonical_deep_link(params: Mapping[str, str]) -> CanonicalDeepLink | None:
    """Parse a complete Canonical entity link with optional rule context."""
    required = (
        "source_snapshot_id",
        "canonical_snapshot_id",
        "canonical_kind",
        "canonical_id",
    )
    if not all(params.get(key) for key in required):
        return None
    try:
        context_rule_id = params.get("context_rule_id")
        return CanonicalDeepLink(
            source_snapshot_id=UUID(params["source_snapshot_id"]),
            canonical_snapshot_id=UUID(params["canonical_snapshot_id"]),
            canonical_kind=TraceCanonicalKind(params["canonical_kind"]),
            canonical_id=UUID(params["canonical_id"]),
            context_rule_id=UUID(context_rule_id) if context_rule_id else None,
        )
    except (ValueError, TypeError):
        return None


def source_excerpt(
    raw_text: str,
    *,
    line_start: int,
    line_end: int,
) -> list[dict[str, Any]]:
    """Return numbered source lines for an inclusive one-based range."""
    lines = raw_text.splitlines()
    if line_start < 1 or line_end < line_start:
        return []
    first_index = line_start - 1
    if first_index >= len(lines):
        return []
    last_index = min(line_end, len(lines))
    return [
        {"line": index + 1, "text": lines[index]}
        for index in range(first_index, last_index)
    ]


def object_value(obj: Mapping[str, Any]) -> str:
    """Build a compact human-readable value for a canonical object."""
    kind = str(obj.get("object_kind") or "")
    if kind in {"addr_group", "service_group"}:
        return "Group"
    if kind in {"any_addr", "any_service"}:
        return "Any"
    if obj.get("cidr"):
        return str(obj["cidr"])
    if obj.get("range_start") or obj.get("range_end"):
        return f"{obj.get('range_start') or '?'} – {obj.get('range_end') or '?'}"
    if obj.get("fqdn"):
        return str(obj["fqdn"])
    protocol = obj.get("protocol")
    port_from = obj.get("port_from")
    port_to = obj.get("port_to")
    if obj.get("icmp_type") is not None:
        return f"ICMP type {obj['icmp_type']}"
    if protocol and port_from is not None:
        port = str(port_from) if port_from == port_to else f"{port_from}–{port_to}"
        return f"{str(protocol).upper()} {port}"
    if protocol:
        return str(protocol).upper()
    return str(obj.get("object_kind") or "Object").replace("_", " ").title()


def ranges_overlap(
    left_start: int,
    left_end: int,
    right_start: int | None,
    right_end: int | None,
) -> bool:
    """Return whether two inclusive source ranges overlap."""
    if right_start is None:
        return False
    resolved_right_end = right_end if right_end is not None else right_start
    return left_start <= resolved_right_end and left_end >= right_start


def compact_uuid(value: str) -> str:
    """Return the first UUID segment for compact technical labels."""
    return value.split("-", maxsplit=1)[0]
