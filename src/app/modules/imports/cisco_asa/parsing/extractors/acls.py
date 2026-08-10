from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.enums import AclUsageType, ProtocolOperandKind
from app.modules.imports.cisco_asa.domain.parsed_config import (
    AclBindingType,
    ParsedAccessRule,
    ZoneInferenceStatus,
)
from app.modules.imports.cisco_asa.parsing.extractors.usage import AclUsageClassifier
from app.modules.imports.cisco_asa.parsing.extractors.zones import (
    ZoneResolution,
    ZoneResolver,
)
from app.modules.imports.cisco_asa.parsing.protocol_operands import (
    ParsedProtocolOperand,
    parse_protocol_operand,
)
from app.modules.imports.cisco_asa.parsing.tokens import parse_modifiers, split_tokens
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree

_ACCESS_LIST_RE = re.compile(
    r"^access-list\s+(?P<acl>\S+)\s+extended\s+(?P<action>permit|deny)\s+"
    r"(?P<proto>\S+)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AclExtractionResult:
    """Container for extended ACL rules extracted from one config tree."""

    rules: list[ParsedAccessRule]


class ExtendedAclExtractor:
    """Parse extended ACL lines into ParsedAccessRule with zone/usage context.

    For each matched line the extractor:
    1. Tokenizes operands and modifiers (inactive, time-range, log)
    2. Classifies protocol via parse_protocol_operand
    3. Normalizes src/dst endpoints to ref tokens understood by the normalizer
    4. Fans out one row per ZoneResolver.resolve_all binding context
    """

    def extract(
        self,
        tree: ConfigTree,
        *,
        zones: ZoneResolver | None = None,
        usage: AclUsageClassifier | None = None,
    ) -> AclExtractionResult:
        """Walk config tree and collect extended ACL rules.

        rule_order increments globally in file order (not per ACL name).
        rule_name is {acl_name}:{rule_order} — later used as base
        canonical rule key input.

        Args:
            tree: Parsed ASA config lines.
            zones: Optional resolver for interface/global bindings and zone labels.
            usage: Optional classifier for firewall vs crypto-map ACL usage.

        Returns:
            All extracted rules; may contain multiple rows per source line when
            an ACL is bound on multiple interfaces (test_tc_08).
        """
        rules: list[ParsedAccessRule] = []
        rule_order = 0

        for node in tree.nodes:
            s = node.line.stripped
            m = _ACCESS_LIST_RE.match(s)
            if not m:
                continue

            rule_order += 1
            acl_name = m.group("acl")
            action = m.group("action").upper()
            proto_token = m.group("proto")
            rest = m.group("rest")

            tokens = split_tokens(rest)
            tokens, mods = parse_modifiers(tokens)

            operand, endpoint_tokens = parse_protocol_operand(proto_token, tokens)
            src_ref, next_idx = self._parse_endpoint(endpoint_tokens, 0)
            dst_ref, next_idx = self._parse_endpoint(endpoint_tokens, next_idx)
            tail = endpoint_tokens[next_idx:]

            service_ref = self._extract_service_ref(operand, tail)

            enabled = not mods.inactive
            zone_resolutions = (
                zones.resolve_all(acl_name)
                if zones
                else [
                    ZoneResolution(
                        src_zone=None,
                        dst_zone=None,
                        unresolved=True,
                        binding_type=AclBindingType.UNKNOWN,
                        zone_inference_status=ZoneInferenceStatus.UNKNOWN,
                        binding_context_key="unbound",
                    )
                ]
            )
            ur = usage.resolve(acl_name) if usage else None

            base_rule_name = f"{acl_name}:{rule_order}"
            for zr in zone_resolutions:
                rules.append(
                    ParsedAccessRule(
                        acl_name=acl_name,
                        rule_name=base_rule_name,
                        action=action,
                        protocol=operand.protocol,
                        src_ref=src_ref,
                        dst_ref=dst_ref,
                        service_ref=service_ref,
                        time_range=mods.time_range,
                        log=mods.log,
                        enabled=enabled,
                        order=rule_order,
                        line_start=node.line.line_no,
                        line_end=node.line.line_no,
                        src_zone=zr.src_zone,
                        dst_zone=zr.dst_zone,
                        unresolved_zone=zr.unresolved,
                        acl_binding_type=zr.binding_type,
                        zone_inference_status=zr.zone_inference_status,
                        protocol_operand_kind=operand.kind,
                        protocol_group_ref=operand.group_ref,
                        protocol_number=operand.protocol_number,
                        acl_usage_type=ur.usage_type if ur else AclUsageType.UNKNOWN,
                        crypto_map_name=ur.crypto_map_name if ur else None,
                        crypto_map_seq=ur.crypto_map_seq if ur else None,
                        raw_line_text=s,
                        binding_context_key=zr.binding_context_key,
                        binding_interface=zr.binding_interface,
                        binding_direction=zr.binding_direction,
                    )
                )

        return AclExtractionResult(rules=rules)

    @staticmethod
    def _is_ipv4(token: str) -> bool:
        """Loose IPv4 token check for host net mask endpoint parsing."""
        return bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", token))

    def _parse_endpoint(self, tokens: list[str], start: int) -> tuple[str, int]:
        """Parse one src or dst operand into a normalizer ref token.

        Output shapes consumed by _ensure_addr_object_from_ref:
        any, host:IP, net:IP/MASK, object/group name, bare token.

        Missing tokens default to any.
        """
        if start >= len(tokens):
            return "any", start

        token = tokens[start]
        lowered = token.lower()

        if lowered in {"any", "any4", "any6"}:
            return "any", start + 1
        if lowered == "object-group" and start + 1 < len(tokens):
            return tokens[start + 1], start + 2
        if lowered == "object" and start + 1 < len(tokens):
            return tokens[start + 1], start + 2
        if lowered == "host" and start + 1 < len(tokens):
            return f"host:{tokens[start + 1]}", start + 2
        if lowered == "interface" and start + 1 < len(tokens):
            return f"interface:{tokens[start + 1]}", start + 2

        if (
            start + 1 < len(tokens)
            and self._is_ipv4(token)
            and self._is_ipv4(tokens[start + 1])
        ):
            return f"net:{token}/{tokens[start + 1]}", start + 2

        return token, start + 1

    @staticmethod
    def _extract_service_ref(  # noqa: C901
        operand: ParsedProtocolOperand,
        tail_tokens: list[str],
    ) -> str | None:
        """Extract port/service operand from ACL tail tokens.

        Uses **last** occurrence of object / object-group / port operators
        in the tail (reverse scan) to match ASA operand ordering on complex lines.

        Returns port literal, range from-to, object/group name, or None
        when protocol implies no L4 service (ip, bare IP protocol number).
        """
        if not tail_tokens:
            if operand.kind == ProtocolOperandKind.IP_PROTOCOL_NUMBER:
                return None
            if operand.kind == ProtocolOperandKind.LITERAL and operand.protocol == "ip":
                return None
            return None

        lowered = [t.lower() for t in tail_tokens]

        if operand.kind == ProtocolOperandKind.IP_PROTOCOL_NUMBER:
            if "object-group" in lowered:
                idx = len(lowered) - 1 - lowered[::-1].index("object-group")
                if idx + 1 < len(tail_tokens):
                    return tail_tokens[idx + 1]
            if "object" in lowered:
                idx = len(lowered) - 1 - lowered[::-1].index("object")
                if idx + 1 < len(tail_tokens):
                    return tail_tokens[idx + 1]
            return None

        if "object-group" in lowered:
            idx = len(lowered) - 1 - lowered[::-1].index("object-group")
            if idx + 1 < len(tail_tokens):
                return tail_tokens[idx + 1]
        if "object" in lowered:
            idx = len(lowered) - 1 - lowered[::-1].index("object")
            if idx + 1 < len(tail_tokens):
                return tail_tokens[idx + 1]

        for operator in ("eq", "lt", "gt", "neq"):
            if operator in lowered:
                idx = len(lowered) - 1 - lowered[::-1].index(operator)
                if idx + 1 < len(tail_tokens):
                    return tail_tokens[idx + 1]

        if "range" in lowered:
            idx = len(lowered) - 1 - lowered[::-1].index("range")
            if idx + 2 < len(tail_tokens):
                return f"{tail_tokens[idx + 1]}-{tail_tokens[idx + 2]}"

        if operand.kind == ProtocolOperandKind.LITERAL and operand.protocol in {
            "icmp",
            "icmp6",
        }:
            if lowered[0] not in {"log", "inactive", "time-range"}:
                return tail_tokens[0]

        return None
