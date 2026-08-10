from __future__ import annotations

from uuid import UUID

from app.modules.canonical.domain import (
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalZone,
    OperandRole,
)
from app.modules.imports.cisco_asa.adapters.normalizer.rules_helpers import (
    append_service_operand_trace,
    emit_rule_zone_issues,
    emit_textual_duplicate_issue,
    validate_protocol_operand,
)
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.adapters.rules.key_builder import (
    DeterministicRuleKeyBuilder,
)
from app.modules.imports.cisco_asa.adapters.rules.processing import (
    build_rule_metadata,
    resolve_rule_processing,
)
from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedAccessRule,
    ParsedConfig,
)
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


class _RuleNormalizationMixin:
    """Mixin that materializes canonical ACL rules and their operands.

    Mutates _NormalizerState in place. Every parsed rule is always
    materialized (rule header + operands + traces) even when
    resolve_rule_processing marks it SKIPPED_FOR_NOW — issues and
    skip metadata are carried in description and trace notes instead.
    """

    def _create_rule_with_trace(
        self,
        *,
        rule: ParsedAccessRule,
        processing_status: str,
        description: str | None,
        key_builder: DeterministicRuleKeyBuilder,
        state: _NormalizerState,
    ) -> CanonicalRule:
        """Create one canonical rule and emit its header trace.

        Called from _materialize_rules after processing status and metadata
        are resolved. DeterministicRuleKeyBuilder assigns stable duplicate
        suffixes (:dupN) when rule.rule_name repeats within one normalize
        pass — both rule_key and name use the builder output.

        Side Effects:
            Appends to state.rules and state.trace_records.
        """
        rule_key = key_builder.build(rule.rule_name)
        canonical_rule = CanonicalRule.create(
            canonical_snapshot_id=state.canonical_snapshot_id,
            rule_key=rule_key,
            name=rule_key,
            action=rule.action,
            enabled=rule.enabled,
            priority=rule.order,
            section=rule.acl_name,
            description=description,
        )
        state.rules.append(canonical_rule)
        state.emit_trace(
            line_start=rule.line_start,
            line_end=rule.line_end,
            canonical_kind=TraceCanonicalKind.RULE,
            canonical_id=canonical_rule.id,
            source_fragment=rule.raw_line_text or None,
            note=f"processing_status={processing_status}",
        )
        return canonical_rule

    def _materialize_rule_zone_operands(
        self,
        *,
        rule: ParsedAccessRule,
        canonical_rule_id: UUID,
        state: _NormalizerState,
    ) -> None:
        """Attach src/dst zone operands when parser inferred zone names.

        Called from _materialize_rules after the rule header exists.
        Global-scope ACL rules typically have empty src_zone/dst_zone;
        in that case no zone operands are created (see test_tc_06 /
        test_tc_08 in test_normalizer_fixtures.py).

        Side Effects:
            May create zones via _ensure_zone and append zone operands.
        """
        if rule.src_zone:
            zone = self._ensure_zone(
                rule.src_zone, source_line=rule.line_start, state=state
            )
            self._add_zone_operand(
                canonical_rule_id,
                zone,
                OperandRole.SRC_ZONE,
                rule.line_start,
                rule.line_end,
                rule.src_zone,
                state,
            )
        if rule.dst_zone:
            zone = self._ensure_zone(
                rule.dst_zone, source_line=rule.line_start, state=state
            )
            self._add_zone_operand(
                canonical_rule_id,
                zone,
                OperandRole.DST_ZONE,
                rule.line_start,
                rule.line_end,
                rule.dst_zone,
                state,
            )

    def _materialize_rule_address_operands(
        self,
        *,
        rule: ParsedAccessRule,
        canonical_rule_id: UUID,
        state: _NormalizerState,
    ) -> None:
        """Attach src/dst address operands via address mixin ref resolution.

        Delegates object lookup/materialization to
        _AddressNormalizationMixin._ensure_addr_object_from_ref, which may
        create inline host/subnet objects or unresolved placeholders.

        Side Effects:
            Appends two CanonicalRuleOperand records and matching traces.
        """
        src_obj_id = self._ensure_addr_object_from_ref(
            rule.src_ref,
            source_line=rule.line_start,
            role=TraceCanonicalRole.SRC_OBJECT.value,
            state=state,
        )
        dst_obj_id = self._ensure_addr_object_from_ref(
            rule.dst_ref,
            source_line=rule.line_start,
            role=TraceCanonicalRole.DST_OBJECT.value,
            state=state,
        )
        for role, obj_id, fragment in (
            (OperandRole.SRC_OBJECT, src_obj_id, rule.src_ref),
            (OperandRole.DST_OBJECT, dst_obj_id, rule.dst_ref),
        ):
            op = CanonicalRuleOperand.create(
                rule_id=canonical_rule_id,
                operand_role=role,
                target_object_id=obj_id,
                position=0,
            )
            state.operands.append(op)
            state.emit_trace(
                line_start=rule.line_start,
                line_end=rule.line_end,
                canonical_kind=TraceCanonicalKind.RULE_OPERAND,
                canonical_id=op.id,
                source_fragment=fragment,
                canonical_role=role.value,
            )

    def _materialize_rules(self, parsed: ParsedConfig, state: _NormalizerState) -> None:
        """Materialize all parsed ACL rules into canonical rules and operands.

        Invoked as the last stage of CiscoAsaNormalizerAdapter.normalize
        after address/service objects (including protocol groups) exist in
        state.objects_by_key.

        Per-rule loop order:
        1. Emit issues (zone, duplicate, protocol validation)
        2. Decide processing status via resolve_rule_processing
        3. Build metadata description for downstream auto-apply gating
        4. Create rule + zone/address/service operands with traces

        Args:
            parsed: Parsed Cisco ASA configuration produced by parser adapter.
            state: Mutable normalization state accumulator shared across helper methods.

        Side Effects:
            Appends rules, operands, zones, issues, and trace records.
        """
        key_builder = DeterministicRuleKeyBuilder()
        for rule in parsed.rules:
            # Issue emission and gating inputs happen before rule materialization.
            emit_rule_zone_issues(rule, state)
            emit_textual_duplicate_issue(rule, state)
            protocol_blocker = validate_protocol_operand(rule, state)
            state.rule_protocol_blockers[rule.rule_name] = protocol_blocker

            processing_status, skip_reasons, auto_apply_eligible = (
                resolve_rule_processing(
                    rule,
                    has_protocol_blocker=protocol_blocker,
                )
            )
            description = build_rule_metadata(
                rule,
                processing_status=processing_status,
                skip_reason_codes=skip_reasons,
                auto_apply_eligible=auto_apply_eligible,
            )
            canonical_rule = self._create_rule_with_trace(
                rule=rule,
                processing_status=processing_status.value,
                description=description,
                key_builder=key_builder,
                state=state,
            )
            self._materialize_rule_zone_operands(
                rule=rule,
                canonical_rule_id=canonical_rule.id,
                state=state,
            )
            self._materialize_rule_address_operands(
                rule=rule,
                canonical_rule_id=canonical_rule.id,
                state=state,
            )
            service_obj_id = self._ensure_service_for_rule(rule, state)
            append_service_operand_trace(
                rule=rule,
                canonical_rule_id=canonical_rule.id,
                service_obj_id=service_obj_id,
                state=state,
            )

    def _ensure_zone(
        self, zone_name: str, *, source_line: int, state: _NormalizerState
    ) -> CanonicalZone:
        """Get or create a canonical zone keyed as zone:{zone_name}.

        Used by _materialize_rule_zone_operands. Zone trace is emitted only
        on first creation so repeated references share one zone entity.

        Side Effects:
            May append a zone and trace record on first sighting.
        """
        key = f"zone:{zone_name}"
        if key not in state.zones_by_key:
            zone = CanonicalZone.create(
                canonical_snapshot_id=state.canonical_snapshot_id,
                zone_key=key,
                name=zone_name,
            )
            state.zones_by_key[key] = zone
            state.emit_trace(
                line_start=source_line,
                line_end=source_line,
                canonical_kind=TraceCanonicalKind.ZONE,
                canonical_id=zone.id,
                source_fragment=zone_name,
                canonical_role=TraceCanonicalRole.FROM_ACL_NAME.value,
                note="zone derived from acl/binding context",
            )
        return state.zones_by_key[key]

    @staticmethod
    def _add_zone_operand(
        rule_id: UUID,
        zone: CanonicalZone,
        role: OperandRole,
        line_start: int,
        line_end: int,
        fragment: str,
        state: _NormalizerState,
    ) -> None:
        """Append one zone operand and its trace record.

        Mirrors the operand+trace pattern in _materialize_rule_address_operands
        but binds target_zone_id instead of target_object_id.
        """
        op = CanonicalRuleOperand.create(
            rule_id=rule_id,
            operand_role=role,
            target_zone_id=zone.id,
            position=0,
        )
        state.operands.append(op)
        state.emit_trace(
            line_start=line_start,
            line_end=line_end,
            canonical_kind=TraceCanonicalKind.RULE_OPERAND,
            canonical_id=op.id,
            source_fragment=fragment,
            canonical_role=role.value,
        )
