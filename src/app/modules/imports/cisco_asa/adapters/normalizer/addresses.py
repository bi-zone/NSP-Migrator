from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.modules.canonical.domain import (
    CanonicalObject,
    ObjectFamily,
    ObjectKind,
)
from app.modules.imports.cisco_asa.adapters.normalizer.address_group_helpers import (
    attach_address_group_member_edge,
    emit_materialized_address_member_objects,
    emit_unresolved_address_group_member_issue,
)
from app.modules.imports.cisco_asa.adapters.normalizer.address_refs import (
    ensure_host_ref,
    ensure_subnet_ref,
    ensure_unresolved_ref,
    resolve_member_ref,
)
from app.modules.imports.cisco_asa.adapters.normalizer.state import (
    _addr_object_from_payload,
    _NormalizerState,
    _ObjectRef,
)
from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedConfig,
    ParsedObjectType,
)
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


class _AddressNormalizationMixin:
    """Mixin that materializes address objects and group membership edges.

    This mixin mutates shared _NormalizerState in place. It intentionally
    splits header materialization and member wiring into separate passes so
    parent group keys exist before child edges are attached.
    """

    def _materialize_address_objects(
        self, parsed: ParsedConfig, state: _NormalizerState
    ) -> None:
        """Materialize parsed structures into canonical objects, members, and traces.

        Called from CiscoAsaNormalizerAdapter.normalize before service and
        rule stages so named address objects exist for later operand resolution.

        Args:
            parsed: Parsed Cisco ASA configuration produced by parser adapter.
            state: Mutable normalization state accumulator shared across helper methods.

        Returns:
            None. The routine mutates provided state in place.

        Side Effects:
            Registers address objects in state.objects_by_key and emits
            header-level object traces.
        """
        for item in parsed.address_objects:
            key = f"addr:{item.name}"
            if item.kind == ParsedObjectType.ADDRESS_GROUP:
                # Group headers are created without members in this pass.
                obj = CanonicalObject.create(
                    canonical_snapshot_id=state.canonical_snapshot_id,
                    object_key=key,
                    object_family=ObjectFamily.ADDR,
                    object_kind=ObjectKind.ADDR_GROUP,
                    name=item.name,
                )
            else:
                obj = _addr_object_from_payload(
                    canonical_snapshot_id=state.canonical_snapshot_id,
                    object_key=key,
                    name=item.name,
                    payload=item.payload,
                )
            state.register(obj)
            state.emit_trace(
                line_start=item.source_line,
                line_end=item.source_line,
                canonical_kind=TraceCanonicalKind.OBJECT,
                canonical_id=obj.id,
                source_fragment=f"object network {item.name}",
                canonical_role=TraceCanonicalRole.HEADER.value,
            )

    def _materialize_address_group_members(
        self, parsed: ParsedConfig, state: _NormalizerState
    ) -> None:
        """Materialize parsed structures into canonical objects, members, and traces.

        Runs after _materialize_address_objects so every parent group key
        from parsed config is already present in state.objects_by_key.

        Args:
            parsed: Parsed Cisco ASA configuration produced by parser adapter.
            state: Mutable normalization state accumulator shared across helper methods.

        Returns:
            None. The routine mutates provided state in place.

        Side Effects:
            Appends group member edges/issues/traces via helper modules in
            address_group_helpers and address_refs.
        """
        for item in parsed.address_objects:
            if item.kind != ParsedObjectType.ADDRESS_GROUP:
                continue
            parent_key = f"addr:{item.name}"
            if parent_key not in state.objects_by_key:
                # Defensive guard: skip orphan member wiring if header was not registered.
                continue
            parent_id = state.objects_by_key[parent_key].object_id

            for pos, member_ref in enumerate(item.payload.get("members", [])):
                # Snapshot keys before resolution to trace only newly materialized objects.
                keys_before = set(state.objects_by_key.keys())
                child_key = self._resolve_member_ref(
                    member_ref,
                    state.canonical_snapshot_id,
                    state.objects_by_key,
                    state.register,
                )
                emit_materialized_address_member_objects(
                    source_line=item.source_line,
                    member_ref=member_ref,
                    keys_before=keys_before,
                    state=state,
                )
                if child_key and child_key in state.objects_by_key:
                    attach_address_group_member_edge(
                        parent_id=parent_id,
                        child_object_id=state.objects_by_key[child_key].object_id,
                        position=pos,
                        source_line=item.source_line,
                        member_ref=member_ref,
                        state=state,
                    )
                elif isinstance(member_ref, str):
                    # Non-string member payloads are ignored silently by design.
                    emit_unresolved_address_group_member_issue(
                        group_name=item.name,
                        member_ref=member_ref,
                        source_line=item.source_line,
                        state=state,
                    )

    def _ensure_addr_object_from_ref(
        self,
        ref: str,
        *,
        source_line: int,
        role: str,
        state: _NormalizerState,
    ) -> UUID:
        """Resolve ACL address operand ref into canonical object id.

        Used by _RuleNormalizationMixin._materialize_rule_address_operands
        for both source and destination rule operands.

        Resolution order:
        - any sentinel
        - inline host: / net: refs
        - named object key lookup
        - unresolved fallback with issue emission
        """
        if ref == "any":
            return state.objects_by_key["addr:any"].object_id
        if ref.startswith("host:"):
            return ensure_host_ref(
                ref=ref,
                source_line=source_line,
                role=role,
                state=state,
            )

        if ref.startswith("net:"):
            return ensure_subnet_ref(
                ref=ref,
                source_line=source_line,
                role=role,
                state=state,
            )

        key = f"addr:{ref}"
        if key in state.objects_by_key:
            return state.objects_by_key[key].object_id
        return ensure_unresolved_ref(
            ref=ref,
            source_line=source_line,
            role=role,
            state=state,
        )

    @staticmethod
    def _resolve_member_ref(
        ref: str,
        canonical_snapshot_id: UUID,
        objects_by_key: dict[str, _ObjectRef],
        register: Callable[[CanonicalObject], CanonicalObject],
    ) -> str | None:
        """Delegate group-member ref resolution to address_refs.resolve_member_ref."""
        return resolve_member_ref(
            ref=ref,
            canonical_snapshot_id=canonical_snapshot_id,
            objects_by_key=objects_by_key,
            register=register,
        )