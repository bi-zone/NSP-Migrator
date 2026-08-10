from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.enums import ProtocolOperandKind

_KNOWN_LITERAL_PROTOCOLS = frozenset(
    {
        "tcp",
        "udp",
        "icmp",
        "icmp6",
        "ip",
        "ah",
        "esp",
        "gre",
        "igmp",
        "eigrp",
        "ospf",
        "pim",
        "sctp",
    }
)


@dataclass(frozen=True, slots=True)
class ParsedProtocolOperand:
    """Structured protocol field from one ACL line.

    Copied onto ParsedAccessRule as protocol_operand_kind,
    protocol_group_ref, and protocol_number by ExtendedAclExtractor.
    """

    kind: ProtocolOperandKind
    protocol: str
    group_ref: str | None = None
    protocol_number: int | None = None


def parse_protocol_operand(
    proto_token: str, rest_tokens: list[str]
) -> tuple[ParsedProtocolOperand, list[str]]:
    """Parse ACL protocol token and optionally consume following tokens.

    Args:
        proto_token: Protocol field from the access-list line (e.g. tcp,
            object-group, 6).
        rest_tokens: Remaining tokens after protocol — for object-group the
            first token is consumed as group_ref.

    Returns:
        Tuple of (operand, remaining_tokens) where remaining_tokens are
        passed to src/dst endpoint parsing in ExtendedAclExtractor.

    Classification rules:
    - object-group [NAME] -> PROTOCOL_GROUP (group_ref may be None)
    - 0–255 decimal -> IP_PROTOCOL_NUMBER
    - known ASA protocol names -> LITERAL
    - other all-digit tokens -> IP_PROTOCOL_NUMBER (including out-of-range;
      normalizer emits protocol_unresolved later)
    - anything else -> LITERAL with lowered token (permissive fallback)
    """
    lowered = proto_token.lower()

    if lowered == "object-group":
        if not rest_tokens:
            return (
                ParsedProtocolOperand(
                    kind=ProtocolOperandKind.PROTOCOL_GROUP,
                    protocol="protocol-group",
                    group_ref=None,
                ),
                rest_tokens,
            )
        group_ref = rest_tokens[0]
        return (
            ParsedProtocolOperand(
                kind=ProtocolOperandKind.PROTOCOL_GROUP,
                protocol="protocol-group",
                group_ref=group_ref,
            ),
            rest_tokens[1:],
        )

    if lowered.isdigit():
        number = int(lowered)
        if 0 <= number <= 255:
            return (
                ParsedProtocolOperand(
                    kind=ProtocolOperandKind.IP_PROTOCOL_NUMBER,
                    protocol=str(number),
                    protocol_number=number,
                ),
                rest_tokens,
            )

    if lowered in _KNOWN_LITERAL_PROTOCOLS:
        return (
            ParsedProtocolOperand(
                kind=ProtocolOperandKind.LITERAL,
                protocol=lowered,
            ),
            rest_tokens,
        )

    if re.fullmatch(r"\d+", lowered):
        # Out-of-range numeric protocols (e.g. 999) — validated in normalizer.
        return (
            ParsedProtocolOperand(
                kind=ProtocolOperandKind.IP_PROTOCOL_NUMBER,
                protocol=lowered,
                protocol_number=int(lowered),
            ),
            rest_tokens,
        )

    return (
        ParsedProtocolOperand(
            kind=ProtocolOperandKind.LITERAL,
            protocol=lowered,
        ),
        rest_tokens,
    )