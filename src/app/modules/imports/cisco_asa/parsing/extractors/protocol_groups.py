from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedObjectType,
    ParsedServiceObject,
)
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree


@dataclass(slots=True)
class ProtocolGroupExtractionResult:
    """Protocol object-groups extracted from indexed object-group protocol headers."""

    protocol_groups: list[ParsedServiceObject]


def _parse_protocol_group_member(stripped: str) -> dict | None:
    """Parse one member line under object-group protocol.

    Recognizes protocol-object (raw protocol token preserved) and
    group-object (nested group name). Returns None for unrecognized
    lines so the caller can accumulate them in raw_lines.
    """
    low = stripped.lower()
    if low.startswith("protocol-object "):
        raw = stripped[len("protocol-object ") :].strip()
        return {"type": "protocol-object", "raw": raw}
    if low.startswith("group-object "):
        return {"type": "group-object", "name": stripped.split(maxsplit=1)[1].strip()}
    return None


class ProtocolGroupExtractor:
    """Extract object-group protocol stanzas as service-family parsed objects."""

    def extract(
        self, tree: ConfigTree, index: AsaIndex
    ) -> ProtocolGroupExtractionResult:
        """Build ParsedServiceObject list from AsaIndex.object_group_protocol.

        Each group's payload contains members (dict list), group_kind
        "protocol", optional description, and optional raw_lines for
        unrecognized body lines.

        Args:
            tree: Parsed configuration tree.
            index: Name->node index from AsaIndex.from_tree.

        Returns:
            Protocol groups with source_line on the header node (trace anchor
            for normalizer membership wiring).
        """
        results: list[ParsedServiceObject] = []

        for name, node_idx in index.object_group_protocol.items():
            source_span = tree.source_span(node_idx)
            group_payload: dict = {"members": [], "group_kind": "protocol"}

            for child in tree.children(node_idx):
                s = child.line.stripped
                if not s:
                    continue
                low = s.lower()
                if low.startswith("description "):
                    group_payload["description"] = s.split(maxsplit=1)[1].strip()
                    continue
                member = _parse_protocol_group_member(s)
                if member is not None:
                    group_payload["members"].append(member)
                else:
                    group_payload.setdefault("raw_lines", []).append(s)

            results.append(
                ParsedServiceObject(
                    name=name,
                    kind=ParsedObjectType.PROTOCOL_GROUP,
                    payload=group_payload,
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        return ProtocolGroupExtractionResult(protocol_groups=results)
