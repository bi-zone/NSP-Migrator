from __future__ import annotations

from app.modules.imports.cisco_asa.domain.enums import (
    AclUsageType,
    IssueReasonCode,
    ProtocolOperandKind,
    RuleProcessingStatus,
)
from app.modules.imports.cisco_asa.domain.parsed_config import (
    AclBindingType,
    ParsedAccessRule,
    ZoneInferenceStatus,
)


def build_rule_metadata(  # noqa: C901
    rule: ParsedAccessRule,
    *,
    processing_status: RuleProcessingStatus,
    skip_reason_codes: list[IssueReasonCode],
    auto_apply_eligible: bool,
) -> str | None:
    """Build semicolon-separated metadata string for CanonicalRule.description.

    Called immediately after resolve_rule_processing in _materialize_rules.
    Downstream tests and roundtrip helpers parse selected keys from this string
    (e.g. acl_binding=global, binding_context=... in
    test_normalizer_fixtures.py, test_roundtrip_canonical_cisco.py).

    Args:
        rule: Parsed ACL rule with binding/usage/protocol context from parser.
        processing_status: FW_APPLICABLE or SKIPPED_FOR_NOW.
        skip_reason_codes: Structured reasons paired with processing_status.
        auto_apply_eligible: Whether rule may enter automatic SD-WAN apply scope.

    Returns:
        Metadata string or None when no parts were produced.
    """
    parts: list[str] = []

    if rule.acl_binding_type == AclBindingType.GLOBAL:
        parts.append("acl_binding=global")
        parts.append("zone_inference=global_scope")
    elif rule.zone_inference_status != ZoneInferenceStatus.UNKNOWN:
        parts.append(f"zone_inference={rule.zone_inference_status.value}")

    parts.append(f"binding_context={rule.binding_context_key}")
    if rule.binding_interface:
        parts.append(f"binding_interface={rule.binding_interface}")
    if rule.binding_direction:
        parts.append(f"binding_direction={rule.binding_direction}")

    parts.append(f"acl_usage={rule.acl_usage_type.value}")
    parts.append(f"processing_status={processing_status.value}")
    parts.append(f"auto_apply_eligible={'true' if auto_apply_eligible else 'false'}")

    if rule.protocol_operand_kind != ProtocolOperandKind.LITERAL:
        parts.append(f"protocol_operand={rule.protocol_operand_kind.value}")
    if rule.protocol_group_ref:
        parts.append(f"protocol_group={rule.protocol_group_ref}")
    if rule.protocol_number is not None:
        parts.append(f"protocol_number={rule.protocol_number}")

    if rule.crypto_map_name:
        parts.append(f"crypto_map={rule.crypto_map_name}:{rule.crypto_map_seq}")

    if skip_reason_codes:
        parts.append(
            "skip_reasons=" + ",".join(code.value for code in skip_reason_codes)
        )

    if rule.time_range:
        parts.append(f"time-range={rule.time_range}")
    if rule.log:
        parts.append("log")

    return "; ".join(parts) if parts else None


def resolve_rule_processing(
    rule: ParsedAccessRule,
    *,
    has_protocol_blocker: bool = False,
) -> tuple[RuleProcessingStatus, list[IssueReasonCode], bool]:
    """Classify whether a parsed rule is firewall-applicable for auto-apply.

    Invoked from _materialize_rules with has_protocol_blocker from
    validate_protocol_operand. Issues are emitted separately in
    rules_helpers; this function only computes structured skip reasons for
    metadata and downstream gating.

    A rule is SKIPPED_FOR_NOW when any skip reason applies. Otherwise it is
    FW_APPLICABLE with auto_apply_eligible=True.

    Note:
        TEXTUAL_DUPLICATE is not a skip reason here — duplicate ACL lines
        still materialize as applicable unless another blocker is present.

    Args:
        rule: Parsed ACL rule.
        has_protocol_blocker: True when protocol operand validation failed.

    Returns:
        Tuple of (processing_status, skip_reason_codes, auto_apply_eligible).
    """
    skip_reasons: list[IssueReasonCode] = []

    if rule.acl_usage_type == AclUsageType.CRYPTO_MAP_SELECTOR:
        skip_reasons.append(IssueReasonCode.CRYPTO_MAP_SELECTOR)

    if rule.acl_usage_type == AclUsageType.CONFLICT:
        skip_reasons.append(IssueReasonCode.USAGE_CONFLICT)

    if rule.zone_inference_status == ZoneInferenceStatus.GLOBAL_SCOPE:
        skip_reasons.append(IssueReasonCode.GLOBAL_SCOPE)

    if (
        rule.unresolved_zone
        and rule.zone_inference_status != ZoneInferenceStatus.GLOBAL_SCOPE
    ):
        # Global ACL uses GLOBAL_SCOPE reason; unresolved_zone applies to interface-bound ACLs only.
        skip_reasons.append(IssueReasonCode.BINDING_MISSING)

    if has_protocol_blocker:
        skip_reasons.append(IssueReasonCode.PROTOCOL_UNRESOLVED)

    if skip_reasons:
        return RuleProcessingStatus.SKIPPED_FOR_NOW, skip_reasons, False

    return RuleProcessingStatus.FW_APPLICABLE, [], True