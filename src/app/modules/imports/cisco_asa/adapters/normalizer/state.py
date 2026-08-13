from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Network
from uuid import UUID

from app.modules.canonical.domain import (
    CanonicalIssue,
    CanonicalObject,
    CanonicalObjectMember,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalZone,
    ObjectFamily,
    ObjectKind,
)
from app.modules.imports.cisco_asa.domain.enums import IssueReasonCode
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord

VENDOR_CODE = "cisco_asa"


@dataclass(slots=True)
class _ObjectRef:
    """Lightweight index entry mapping canonical object key to id.

    Stored in _NormalizerState.objects_by_key so member-resolution helpers
    (address_refs.resolve_member_ref, materialize_service_group_member)
    can look up or register objects without holding full CanonicalObject
    instances in every dict value.
    """

    key: str
    object_id: UUID


def _mask_to_prefix(mask: str) -> int | None:
    """Convert ASA dotted-decimal mask to CIDR prefix length.

    Shared by _addr_object_from_payload and address_refs.ensure_subnet_ref.
    Returns None for invalid masks instead of raising — callers decide fallback
    semantics (ip/0 for parsed headers, addr:any for ACL operands).
    """
    try:
        return int(IPv4Network(f"0.0.0.0/{mask}").prefixlen)
    except Exception:
        return None


def _addr_object_from_payload(
    canonical_snapshot_id: UUID,
    object_key: str,
    name: str,
    payload: dict,
) -> CanonicalObject:
    """Build a canonical address object from parsed object network payload.

    Called from _AddressNormalizationMixin._materialize_address_objects for
    non-group address headers already parsed by the ASA adapter.

    Unknown payload['type'] values become UNRESOLVED_ADDR so import continues
    without widening the object to an address wildcard.

    Note:
        Invalid subnet masks become UNRESOLVED_ADDR. ACL operand subnet refs
        use the same unresolved semantics in ensure_subnet_ref.
    """
    kind = payload.get("type")

    if kind == "host":
        ip = payload["ip"]
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.HOST,
            name=name,
            ip_version=4,
            cidr=f"{ip}/32",
        )

    if kind == "subnet":
        ip = payload["ip"]
        mask = payload["mask"]
        prefix = _mask_to_prefix(mask)
        if prefix is None:
            return CanonicalObject.create(
                canonical_snapshot_id=canonical_snapshot_id,
                object_key=object_key,
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.UNRESOLVED_ADDR,
                name=name,
                description=f"invalid ASA subnet mask: {ip} {mask}",
            )
        cidr = f"{ip}/{prefix}"
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.SUBNET,
            name=cidr,
            ip_version=4,
            cidr=cidr,
        )

    if kind == "range":
        start = payload["start"]
        end = payload["end"]
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.RANGE,
            name=f"{start}-{end}",
            ip_version=4,
            range_start=start,
            range_end=end,
        )

    if kind == "fqdn":
        fqdn = payload["name"]
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.FQDN,
            name=fqdn,
            fqdn=fqdn,
        )

    return CanonicalObject.create(
        canonical_snapshot_id=canonical_snapshot_id,
        object_key=object_key,
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.UNRESOLVED_ADDR,
        name=name,
        description="unsupported ASA address object payload",
    )


@dataclass
class _NormalizerState:
    """In-memory accumulator for one normalize pass.

    Created in CiscoAsaNormalizerAdapter.normalize and consumed by all
    normalizer mixins. At the end of the pass, lists/dicts are copied into
    SaveCanonicalSnapshotCommand and SaveTraceRecordsCommand.

    Attributes:
        canonical_snapshot_id: Id assigned to all entities in this output snapshot.
        source_snapshot_id: Parsed config snapshot being normalized.
        normalizer_code/normalizer_version: Persisted into trace/issue metadata.
        issues: Canonical migration diagnostics (also mirrored as ISSUE traces).
        zones_by_key: Deduplicated zones keyed as zone:{name}.
        objects_by_key/objects_by_id: Canonical object registry with id lookup.
        object_members: Parent->child group membership edges.
        trace_records: Line-level raw->canonical lineage records.
        rules/operands: Materialized ACL rules and their operand bindings.
        rule_protocol_blockers: Per-rule protocol validation flag written in
            rules.py during validate_protocol_operand (True = blocked).
        textual_rule_signatures: Duplicate ACL line detection map used by
            rules_helpers.emit_textual_duplicate_issue.
    """

    canonical_snapshot_id: UUID
    source_snapshot_id: UUID
    normalizer_code: str
    normalizer_version: str
    issues: list[CanonicalIssue] = field(default_factory=list)
    zones_by_key: dict[str, CanonicalZone] = field(default_factory=dict)
    objects_by_key: dict[str, _ObjectRef] = field(default_factory=dict)
    objects_by_id: dict[UUID, CanonicalObject] = field(default_factory=dict)
    object_members: list[CanonicalObjectMember] = field(default_factory=list)
    trace_records: list[TraceRawToCanonicalRecord] = field(default_factory=list)
    rules: list[CanonicalRule] = field(default_factory=list)
    operands: list[CanonicalRuleOperand] = field(default_factory=list)
    rule_protocol_blockers: dict[str, bool] = field(default_factory=dict)
    textual_rule_signatures: dict[tuple[str, str, str], str] = field(
        default_factory=dict
    )

    def register(self, obj: CanonicalObject) -> CanonicalObject:
        """Register a canonical object, deduplicating by object_key.

        Idempotent: repeated registration of the same key returns the first object
        without replacing it. Passed as register= callback into member
        materializers in services.py and address_refs.py.

        Returns:
            The registered object (existing or newly inserted).
        """
        existing = self.objects_by_key.get(obj.object_key)
        if existing is not None:
            return self.objects_by_id[existing.object_id]

        self.objects_by_id[obj.id] = obj
        self.objects_by_key[obj.object_key] = _ObjectRef(
            key=obj.object_key, object_id=obj.id
        )
        return obj

    def emit_trace(
        self,
        *,
        line_start: int,
        line_end: int,
        canonical_kind: TraceCanonicalKind,
        canonical_id: UUID,
        source_fragment: str | None = None,
        canonical_role: str | None = None,
        note: str | None = None,
    ) -> None:
        """Append one raw->canonical lineage trace record.

        Central trace writer for the normalizer. Called from every mixin and
        helper when objects, operands, members, or rules are materialized.
                Records with line_start < 1 are dropped silently (guard for missing
        source line metadata).
        """
        if line_start < 1:
            return
        self.trace_records.append(
            TraceRawToCanonicalRecord.create(
                source_snapshot_id=self.source_snapshot_id,
                canonical_snapshot_id=self.canonical_snapshot_id,
                vendor_code=VENDOR_CODE,
                normalizer_code=self.normalizer_code,
                normalizer_version=self.normalizer_version,
                source_line_start=line_start,
                source_line_end=line_end,
                canonical_kind=canonical_kind,
                canonical_id=canonical_id,
                source_fragment=source_fragment,
                canonical_role=canonical_role,
                note=note,
            )
        )

    def emit_issue(
        self,
        *,
        entity_type: str,
        issue_code: str,
        message: str,
        entity_key: str | None = None,
        source_line_start: int | None = None,
        source_line_end: int | None = None,
        source_fragment: str | None = None,
        reason: IssueReasonCode | None = None,
    ) -> CanonicalIssue:
        """Create a canonical issue and mirror it as an ISSUE trace.

        Single entry point for normalizer diagnostics. issue_code values are
        stable contracts asserted across tests/imports/cisco_asa/.

        When reason is set, it is prefixed onto message as
        [{reason.value}] ... for downstream filtering while preserving the
        original human-readable text.

        Side Effects:
            Appends to issues and trace_records (via emit_trace).

        Returns:
            The created CanonicalIssue.
        """
        if reason is not None:
            message = f"[{reason.value}] {message}"
        issue = CanonicalIssue.create(
            canonical_snapshot_id=self.canonical_snapshot_id,
            entity_type=entity_type,
            entity_key=entity_key,
            issue_code=issue_code,
            message=message,
            source_line_start=source_line_start,
            source_line_end=source_line_end,
        )
        self.issues.append(issue)
        self.emit_trace(
            line_start=source_line_start or 1,
            line_end=source_line_end or source_line_start or 1,
            canonical_kind=TraceCanonicalKind.ISSUE,
            canonical_id=issue.id,
            source_fragment=source_fragment,
            note=f"issue: {issue_code}",
        )
        return issue
