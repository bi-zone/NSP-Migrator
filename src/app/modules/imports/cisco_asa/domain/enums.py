from __future__ import annotations

from enum import StrEnum


class ProtocolOperandKind(StrEnum):
    """How the protocol field on an ACL line was parsed.

    Set on ParsedAccessRule.protocol_operand_kind by
    parsing/protocol_operands.py and consumed by service materialization
    (normalizer/services.py) and validate_protocol_operand.
    """

    LITERAL = "literal"
    """Named protocol token (tcp, udp, icmp, ip, …)."""

    PROTOCOL_GROUP = "protocol_group"
    """Operand references an object-group protocol — may include port/service ref."""

    SERVICE_OBJECT = "service_object"
    """Operand references a named service object in the ACL protocol slot."""

    IP_PROTOCOL_NUMBER = "ip_protocol_number"
    """Numeric IP protocol (permit 6 …) — materialized via build_ip_protocol_service."""


class AclUsageType(StrEnum):
    """Whether an ACL is used as firewall policy, crypto-map selector, or both.

    Resolved in parsing/extractors/usage.py and stored on
    ParsedAccessRule.acl_usage_type. Drives skip logic in
    resolve_rule_processing and informational issues in rules_helpers.
    """

    FIREWALL_POLICY = "firewall_policy"
    """ACL bound via access-group — normal firewall migration candidate."""

    CRYPTO_MAP_SELECTOR = "crypto_map_selector"
    """ACL referenced only from crypto map — excluded from auto-apply scope."""

    UNKNOWN = "unknown"
    """Usage could not be classified from config bindings."""

    CONFLICT = "conflict"
    """ACL referenced by both firewall policy and crypto map."""


class RuleProcessingStatus(StrEnum):
    """Firewall auto-apply eligibility for one canonicalized ACL rule.

    Computed in resolve_rule_processing and serialized into
    CanonicalRule.description as processing_status=.... Does not suppress
    rule materialization — skipped rules still get operands and traces.
    """

    FW_APPLICABLE = "fw_applicable"
    """No blocking skip reasons — eligible for downstream firewall auto-apply."""

    SKIPPED_FOR_NOW = "skipped_for_now"
    """Has skip reasons (zones, usage, protocol) — manual review path."""


class IssueReasonCode(StrEnum):
    """Structured reason taxonomy attached to canonical issues and rule metadata.

    Passed to emit_issue(reason=...) across normalizer helpers. When set,
    _NormalizerState.emit_issue prefixes [{value}] onto the message.
    Overlapping values also appear in skip_reasons inside rule descriptions.
    """

    BINDING_MISSING = "binding_missing"
    """Interface ACL where src/dst zones could not be inferred (not global scope)."""

    MAPPING_MISSING = "mapping_missing"
    """Referenced object/group member or service ref could not be resolved."""

    PROTOCOL_UNRESOLVED = "protocol_unresolved"
    """Protocol operand invalid or protocol object-group missing."""

    USAGE_CONFLICT = "usage_conflict"
    """ACL used as both firewall policy and crypto-map selector."""

    CRYPTO_MAP_SELECTOR = "crypto_map_selector"
    """ACL is crypto-map-only selector — skipped for firewall auto-apply."""

    GLOBAL_SCOPE = "global_scope"
    """Global ACL binding — zones intentionally non-directional."""

    TEXTUAL_DUPLICATE = "textual_duplicate"
    """Duplicate raw ACL line in same ACL + binding context."""
