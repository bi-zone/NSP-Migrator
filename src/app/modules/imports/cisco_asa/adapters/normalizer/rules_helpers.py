from __future__ import annotations

from app.modules.canonical.domain import CanonicalRuleOperand, OperandRole
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.domain.enums import (
    AclUsageType,
    IssueReasonCode,
    ProtocolOperandKind,
)
from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedAccessRule,
    ZoneInferenceStatus,
)
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole


def emit_rule_zone_issues(rule: ParsedAccessRule, state: _NormalizerState) -> None:
    """Emit zone-binding and ACL-usage issues for one parsed rule.

    Invoked as the first helper in _materialize_rules for every
    ParsedAccessRule. Issues are informational for migration review; the
    canonical rule is still created afterward.

    Zone branch is mutually exclusive:
    - GLOBAL_SCOPE -> global_acl_scope_no_interface_zones (not unresolved_zone)
    - otherwise unresolved binding -> unresolved_zone

    ACL usage checks are independent and may stack with a zone issue.

    Side Effects:
        Appends CanonicalIssue records to state.issues.

    Stable contracts:
        issue_code values are asserted in tests/imports/cisco_asa/
    """
    if rule.zone_inference_status == ZoneInferenceStatus.GLOBAL_SCOPE:
        state.emit_issue(
            entity_type="cisco_asa_rule",
            issue_code="global_acl_scope_no_interface_zones",
            message=(
                "Rule is bound to a global ACL; interface zones are not "
                "directional and require separate SD-WAN zone assignment"
            ),
            entity_key=rule.rule_name,
            source_line_start=rule.line_start,
            source_line_end=rule.line_end,
            reason=IssueReasonCode.GLOBAL_SCOPE,
        )
    elif rule.unresolved_zone:
        # Interface-bound ACL where src/dst zones could not be inferred.
        state.emit_issue(
            entity_type="cisco_asa_rule",
            issue_code="unresolved_zone",
            message="Zone cannot be resolved from ACL binding/name",
            entity_key=rule.rule_name,
            source_line_start=rule.line_start,
            source_line_end=rule.line_end,
            reason=IssueReasonCode.BINDING_MISSING,
        )

    if rule.acl_usage_type == AclUsageType.CONFLICT:
        state.emit_issue(
            entity_type="cisco_asa_rule",
            issue_code="usage_conflict",
            message=(
                f"ACL {rule.acl_name} is referenced by both firewall policy "
                f"and crypto map {rule.crypto_map_name}"
            ),
            entity_key=rule.rule_name,
            source_line_start=rule.line_start,
            source_line_end=rule.line_end,
            reason=IssueReasonCode.USAGE_CONFLICT,
        )

    if rule.acl_usage_type == AclUsageType.CRYPTO_MAP_SELECTOR:
        state.emit_issue(
            entity_type="cisco_asa_rule",
            issue_code="crypto_map_selector",
            message=(
                f"ACL {rule.acl_name} is a crypto-map selector "
                f"({rule.crypto_map_name} {rule.crypto_map_seq}); "
                "excluded from firewall auto-apply scope"
            ),
            entity_key=rule.rule_name,
            source_line_start=rule.line_start,
            source_line_end=rule.line_end,
            reason=IssueReasonCode.CRYPTO_MAP_SELECTOR,
        )


def emit_textual_duplicate_issue(rule: ParsedAccessRule, state: _NormalizerState) -> None:
    """Detect duplicate raw ACL lines within the same ACL and binding context.

    Signature key: (acl_name, binding_context_key, normalized raw line).
    First occurrence is recorded in state.textual_rule_signatures; later
    matches emit textual_duplicate_rule referencing the first rule name.

    Duplicate detection does not suppress canonical rule creation — both rules
    remain materialized with operands and traces.

    Side Effects:
        May update state.textual_rule_signatures or append an issue.
    """
    normalized_line = " ".join(rule.raw_line_text.split()).lower()
    signature = (
        rule.acl_name,
        rule.binding_context_key,
        normalized_line,
    )
    first_seen_key = state.textual_rule_signatures.get(signature)
    if first_seen_key is None:
        state.textual_rule_signatures[signature] = rule.rule_name
        return

    state.emit_issue(
        entity_type="cisco_asa_rule",
        issue_code="textual_duplicate_rule",
        message=(
            "Textual duplicate ACL line in same ACL and binding context; "
            f"first seen as {first_seen_key}"
        ),
        entity_key=rule.rule_name,
        source_line_start=rule.line_start,
        source_line_end=rule.line_end,
        source_fragment=rule.raw_line_text,
        reason=IssueReasonCode.TEXTUAL_DUPLICATE,
    )


def validate_protocol_operand(rule: ParsedAccessRule, state: _NormalizerState) -> bool:
    """Validate protocol operand and return whether auto-apply should be blocked.

    Called before resolve_rule_processing in _materialize_rules. Return
    value semantics are inverted from typical validators:

    - True : protocol issue emitted; rule should be treated as blocked
    - False : no protocol blocker for this rule

    The blocker flag is stored in state.rule_protocol_blockers and passed to
    resolve_rule_processing(has_protocol_blocker=...), which may mark the
    rule SKIPPED_FOR_NOW.

    Protocol object-group lookup uses service:{ref} keys populated by earlier
    service/protocol materialization stages in orchestrator.py.

    Side Effects:
        Appends protocol-related issues on validation failure.
    """
    if rule.protocol_operand_kind == ProtocolOperandKind.PROTOCOL_GROUP:
        if not rule.protocol_group_ref:
            state.emit_issue(
                entity_type="cisco_asa_rule",
                issue_code="protocol_unresolved",
                message="Protocol object-group reference is missing",
                entity_key=rule.rule_name,
                source_line_start=rule.line_start,
                source_line_end=rule.line_end,
                reason=IssueReasonCode.PROTOCOL_UNRESOLVED,
            )
            return True
        group_key = f"service:{rule.protocol_group_ref}"
        if group_key not in state.objects_by_key:
            state.emit_issue(
                entity_type="cisco_asa_rule",
                issue_code="protocol_mapping_missing",
                message=f"Protocol object-group not found: {rule.protocol_group_ref}",
                entity_key=rule.rule_name,
                source_line_start=rule.line_start,
                source_line_end=rule.line_end,
                reason=IssueReasonCode.MAPPING_MISSING,
            )
            return True

    if rule.protocol_operand_kind == ProtocolOperandKind.IP_PROTOCOL_NUMBER:
        if rule.protocol_number is None or not 0 <= rule.protocol_number <= 255:
            state.emit_issue(
                entity_type="cisco_asa_rule",
                issue_code="protocol_unresolved",
                message=f"Invalid IP protocol number: {rule.protocol}",
                entity_key=rule.rule_name,
                source_line_start=rule.line_start,
                source_line_end=rule.line_end,
                reason=IssueReasonCode.PROTOCOL_UNRESOLVED,
            )
            return True

    return False


def append_service_operand_trace(
    *,
    rule: ParsedAccessRule,
    canonical_rule_id,
    service_obj_id,
    state: _NormalizerState,
) -> None:
    """Append service operand and trace after service object resolution.

    Final step of per-rule materialization in _materialize_rules, called
    immediately after _ensure_service_for_rule resolves service_obj_id.

    Service operand is always appended, including for skipped rules, so trace
    coverage stays complete even when auto-apply is disabled.
        Side Effects:
        Appends one CanonicalRuleOperand and one trace record.
    """
    svc_op = CanonicalRuleOperand.create(
        rule_id=canonical_rule_id,
        operand_role=OperandRole.SERVICE,
        target_object_id=service_obj_id,
        position=0,
    )
    state.operands.append(svc_op)
    state.emit_trace(
        line_start=rule.line_start,
        line_end=rule.line_end,
        canonical_kind=TraceCanonicalKind.RULE_OPERAND,
        canonical_id=svc_op.id,
        source_fragment=rule.service_ref or rule.protocol,
        canonical_role=TraceCanonicalRole.SERVICE.value,
        note=f"protocol_operand={rule.protocol_operand_kind.value}",
    )