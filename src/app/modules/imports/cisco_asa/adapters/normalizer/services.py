from __future__ import annotations

from uuid import UUID

from app.modules.canonical.domain import (
    CanonicalObject,
    ObjectFamily,
    ObjectKind,
)
from app.modules.imports.cisco_asa.adapters.normalizer.service_group_helpers import (
    attach_group_member_edges,
    emit_materialized_member_objects,
    emit_unresolved_member_issue,
)
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.adapters.services.facade import (
    build_inline_service_from_ref,
    build_ip_protocol_service,
    canonical_object_for_parsed_service,
    materialize_service_group_member,
)
from app.modules.imports.cisco_asa.domain.enums import (
    IssueReasonCode,
    ProtocolOperandKind,
)
from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedAccessRule,
    ParsedConfig,
    ParsedObjectType,
)
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


class _ServiceNormalizationMixin:
    """Mixin that materializes service objects, group edges, and rule operands.

    Mutates _NormalizerState in place. Object building delegates to
    adapters/services/facade; trace/issue/edge emission for group members
    delegates to service_group_helpers.
    """

    @staticmethod
    def _emit_service_object_trace(
        *,
        source_line: int,
        object_id: UUID,
        source_fragment: str,
        note: str,
        state: _NormalizerState,
    ) -> None:
        """Emit an OBJECT trace for a service created during rule resolution.

        Used when ACL operands materialize inline or fallback service objects
        (not for parsed object headers, which use TraceCanonicalRole.HEADER).
        """
        state.emit_trace(
            line_start=source_line,
            line_end=source_line,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=object_id,
            source_fragment=source_fragment,
            canonical_role=TraceCanonicalRole.SERVICE.value,
            note=note,
        )

    @staticmethod
    def _service_trace_fragment(
        kind: ParsedObjectType, name: str, payload: dict
    ) -> str:
        """Reconstruct ASA source fragment for service object header traces.

        Called from _materialize_service_objects so trace records mirror
        the original object service / object-group stanza wording.
        """
        if kind == ParsedObjectType.SERVICE_GROUP:
            if payload.get("group_kind") == "icmp-type":
                return f"object-group icmp-type {name}"
            return f"object-group service {name}"
        if kind == ParsedObjectType.PROTOCOL_GROUP:
            return f"object-group protocol {name}"
        return f"object service {name}"

    def _materialize_service_objects(
        self, parsed: ParsedConfig, state: _NormalizerState
    ) -> None:
        """Register canonical service/protocol object headers from parsed config.

        Invoked from CiscoAsaNormalizerAdapter.normalize before group-member
        wiring so service:{name} keys exist for later edge attachment and
        rule operand lookup (see test_tc_04 in test_normalizer_fixtures.py).

        Side Effects:
            Registers objects and emits header-level OBJECT traces.
        """
        for svc_item in parsed.service_objects:
            obj = canonical_object_for_parsed_service(
                canonical_snapshot_id=state.canonical_snapshot_id,
                svc_item=svc_item,
            )
            state.register(obj)
            fragment = self._service_trace_fragment(
                svc_item.kind, svc_item.name, svc_item.payload
            )
            state.emit_trace(
                line_start=svc_item.source_line,
                line_end=svc_item.source_line,
                canonical_kind=TraceCanonicalKind.OBJECT,
                canonical_id=obj.id,
                source_fragment=fragment,
                canonical_role=TraceCanonicalRole.HEADER.value,
            )

    def _materialize_service_group_members(
        self, parsed: ParsedConfig, state: _NormalizerState
    ) -> None:
        """Wire membership edges for parsed service object-groups.

        Runs after _materialize_service_objects. Passes group-level
        protocol from payload into member materialization (needed for
        port-object parsing context).

        Side Effects:
            May create child service objects, edges, issues, and traces.
        """
        for svc_item in parsed.service_objects:
            if svc_item.kind != ParsedObjectType.SERVICE_GROUP:
                continue
            self._attach_group_members(
                svc_item.name,
                svc_item.payload.get("members", []),
                svc_item.payload.get("protocol"),
                svc_item.source_line,
                state,
                entity_type="cisco_asa_service_group",
            )

    def _materialize_protocol_group_members(
        self, parsed: ParsedConfig, state: _NormalizerState
    ) -> None:
        """Wire membership edges for parsed protocol object-groups.

        Same member pipeline as service groups but without inherited group
        protocol context (group_protocol=None).

        Side Effects:
            May create child protocol service objects, edges, issues, and traces.
        """
        for svc_item in parsed.service_objects:
            if svc_item.kind != ParsedObjectType.PROTOCOL_GROUP:
                continue
            self._attach_group_members(
                svc_item.name,
                svc_item.payload.get("members", []),
                None,
                svc_item.source_line,
                state,
                entity_type="cisco_asa_protocol_group",
            )

    def _attach_group_members(
        self,
        group_name: str,
        members: list[object],
        group_protocol: str | None,
        source_line: int,
        state: _NormalizerState,
        *,
        entity_type: str,
    ) -> None:
        """Resolve and attach one group's member list to canonical edges.

        Shared by service-group and protocol-group stages. Delegates member
        parsing/materialization to materialize_service_group_member and
        trace/issue/edge emission to service_group_helpers.

        Args:
            entity_type: Issue taxonomy discriminator passed to
                emit_unresolved_member_issue (service vs protocol group).

        Side Effects:
            Mutates state.objects_by_key, object_members, issues, traces.
        """
        parent_key = f"service:{group_name}"
        if parent_key not in state.objects_by_key:
            # Header stage did not register this group — skip silently.
            return
        parent_id = state.objects_by_key[parent_key].object_id

        for pos, member in enumerate(members):
            if not isinstance(member, dict):
                continue
            keys_before = set(state.objects_by_key.keys())
            child_keys = materialize_service_group_member(
                member,
                canonical_snapshot_id=state.canonical_snapshot_id,
                group_protocol=group_protocol,
                objects_by_key=state.objects_by_key,
                register=state.register,
            )
            emit_materialized_member_objects(
                source_line=source_line,
                member=member,
                keys_before=keys_before,
                state=state,
            )
            if not child_keys:
                emit_unresolved_member_issue(
                    group_name=group_name,
                    member=member,
                    source_line=source_line,
                    entity_type=entity_type,
                    state=state,
                )
                continue

            attach_group_member_edges(
                parent_id=parent_id,
                child_keys=child_keys,
                pos=pos,
                source_line=source_line,
                member=member,
                state=state,
            )

    def _ensure_service_for_rule(
        self, rule: ParsedAccessRule, state: _NormalizerState
    ) -> UUID:
        """Resolve the service object id for one ACL rule operand.

        Called from _RuleNormalizationMixin._materialize_rules before
        append_service_operand_trace. Branches on rule.protocol_operand_kind
        to pick numeric protocol, protocol-group, or literal service resolution.

        Returns:
            Canonical service object id (may be sentinel service:any or
            unresolved placeholder).
        """
        if rule.protocol_operand_kind == ProtocolOperandKind.IP_PROTOCOL_NUMBER:
            return self._ensure_ip_protocol_service(rule, state)

        if rule.protocol_operand_kind == ProtocolOperandKind.PROTOCOL_GROUP:
            if rule.service_ref:
                # e.g. permit object-group PG tcp eq 443 — group sets protocol context.
                effective_protocol = self._effective_protocol_from_group(rule, state)
                return self._ensure_service_object_from_ref(
                    effective_protocol or "ip",
                    rule.service_ref,
                    source_line=rule.line_start,
                    state=state,
                )
            return self._ensure_protocol_group_service(rule, state)

        return self._ensure_service_object_from_ref(
            rule.protocol,
            rule.service_ref,
            source_line=rule.line_start,
            state=state,
        )

    def _effective_protocol_from_group(
        self, rule: ParsedAccessRule, state: _NormalizerState
    ) -> str | None:
        """Read inherited protocol from a materialized protocol object-group.

        Used when an ACL line references both protocol_group_ref and a
        port/service operand (service_ref).
        """
        if not rule.protocol_group_ref:
            return None
        group_key = f"service:{rule.protocol_group_ref}"
        group_ref = state.objects_by_key.get(group_key)
        if group_ref is None:
            return None
        group_obj = state.objects_by_id[group_ref.object_id]
        return group_obj.protocol

    def _ensure_ip_protocol_service(
        self, rule: ParsedAccessRule, state: _NormalizerState
    ) -> UUID:
        """Resolve service for numeric IP-protocol ACL operands.

        Prefers named service lookup, then materializes a protocol-number object,
        then falls back to service:any when the number is missing/invalid
        (protocol issues are emitted separately in validate_protocol_operand).
        """
        existing_service_id = self._lookup_named_service_ref(rule.service_ref, state)
        if existing_service_id is not None:
            return existing_service_id

        if rule.protocol_number is not None:
            built = build_ip_protocol_service(
                canonical_snapshot_id=state.canonical_snapshot_id,
                protocol_number=rule.protocol_number,
            )
            built = state.register(built)
            self._emit_service_object_trace(
                source_line=rule.line_start,
                object_id=built.id,
                source_fragment=f"protocol {rule.protocol_number}",
                note="IP protocol number materialized from ACL operand",
                state=state,
            )
            return built.id

        return state.objects_by_key["service:any"].object_id

    def _ensure_protocol_group_service(
        self, rule: ParsedAccessRule, state: _NormalizerState
    ) -> UUID:
        """Return protocol-group object when ACL operand is the group itself.

        Used for lines like permit object-group MY_PROTO any any with no
        separate port/service ref. Missing groups fall back to service:any
        without emitting unresolved_service_ref (group issues come from
        validate_protocol_operand instead).
        """
        if not rule.protocol_group_ref:
            return state.objects_by_key["service:any"].object_id
        key = f"service:{rule.protocol_group_ref}"
        if key in state.objects_by_key:
            return state.objects_by_key[key].object_id
        return state.objects_by_key["service:any"].object_id

    def _ensure_service_object_from_ref(
        self,
        protocol: str,
        ref: str | None,
        *,
        source_line: int,
        state: _NormalizerState,
    ) -> UUID:
        """Resolve named or inline service reference for an ACL operand.

        Resolution order: default/any -> named lookup -> inline build -> unresolved
        placeholder with unresolved_service_ref issue.

        Side Effects:
            May register inline/unresolved objects and emit traces/issues.
        """
        if not ref or ref == "any":
            return self._ensure_default_service_object(
                protocol=protocol,
                source_line=source_line,
                state=state,
            )

        existing_service_id = self._lookup_named_service_ref(ref, state)
        if existing_service_id is not None:
            return existing_service_id

        inline = build_inline_service_from_ref(
            canonical_snapshot_id=state.canonical_snapshot_id,
            protocol=protocol,
            ref=ref,
        )
        if inline is not None:
            inline = state.register(inline)
            self._emit_service_object_trace(
                source_line=source_line,
                object_id=inline.id,
                source_fragment=f"{protocol} {ref}",
                note="inline service materialized from ACL operand",
                state=state,
            )
            return inline.id

        return self._ensure_unresolved_service_object(
            ref=ref,
            protocol=protocol,
            source_line=source_line,
            state=state,
        )

    @staticmethod
    def _lookup_named_service_ref(ref: str | None, state: _NormalizerState) -> UUID | None:
        """Look up pre-materialized service object by service:{ref} key."""
        if not ref:
            return None
        key = f"service:{ref}"
        if key in state.objects_by_key:
            return state.objects_by_key[key].object_id
        return None

    def _ensure_default_service_object(
        self,
        *,
        protocol: str,
        source_line: int,
        state: _NormalizerState,
    ) -> UUID:
        """Return default service when ACL operand has no port/service ref.

        For protocol=ip materializes an implicit IP service object instead
        of the permissive service:any sentinel. Other protocols reuse
        service:any registered in _register_sentinel_objects.
        """
        if protocol != "ip":
            return state.objects_by_key["service:any"].object_id

        built = build_ip_protocol_service(
            canonical_snapshot_id=state.canonical_snapshot_id,
            protocol_name="ip",
        )
        built = state.register(built)
        self._emit_service_object_trace(
            source_line=source_line,
            object_id=built.id,
            source_fragment="ip",
            note="implicit ip protocol service for ACL rule",
            state=state,
        )
        return built.id

    def _ensure_unresolved_service_object(
        self,
        *,
        ref: str,
        protocol: str,
        source_line: int,
        state: _NormalizerState,
    ) -> UUID:
        """Create or reuse unresolved service placeholder for unknown refs.

        Ensures normalization continues with a stable service:unresolved:{ref}
        object rather than silently mapping to service:any (see
        test_unresolved_service_ref_not_any_service_permissive).

        Side Effects:
            Registers fallback object, trace, and unresolved_service_ref issue.
        """
        unresolved_key = f"service:unresolved:{ref}"
        if unresolved_key in state.objects_by_key:
            return state.objects_by_key[unresolved_key].object_id

        fallback = CanonicalObject.create(
            canonical_snapshot_id=state.canonical_snapshot_id,
            object_key=unresolved_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.UNRESOLVED_SERVICE,
            name=ref,
            protocol=protocol if protocol else None,
            description="unresolved ASA service reference",
        )
        state.register(fallback)
        self._emit_service_object_trace(
            source_line=source_line,
            object_id=fallback.id,
            source_fragment=ref,
            note="unresolved service reference fallback",
            state=state,
        )
        state.emit_issue(
            entity_type="cisco_asa_rule",
            issue_code="unresolved_service_ref",
            message=f"Unresolved ASA service reference: {ref}",
            entity_key=ref,
            source_line_start=source_line,
            source_line_end=source_line,
            reason=IssueReasonCode.MAPPING_MISSING,
        )
        return fallback.id
