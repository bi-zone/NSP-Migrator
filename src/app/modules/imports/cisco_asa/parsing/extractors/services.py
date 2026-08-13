from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedObjectType,
    ParsedServiceObject,
)
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.service_members import (
    parse_inline_service_object,
)
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree


@dataclass(slots=True)
class ServiceExtractionResult:
    """Service objects and groups extracted from indexed service-family headers."""

    services: list[ParsedServiceObject]


def _parse_service_line(stripped: str) -> dict:
    """Parse service <proto> ... body line under object service.

    Produces payload dicts for build_canonical_service_from_payload during
    header materialization. Supports tcp/udp/tcp-udp port ops, icmp types,
    and bare ip/esp. Unrecognized tail tokens are stored in raw.
    """
    parts = stripped.split()
    if not parts or parts[0].lower() != "service":
        return {}

    if len(parts) < 2:
        return {}

    payload = parse_inline_service_object(" ".join(parts[1:]))
    return payload or {}


def _parse_service_group_member(stripped: str) -> dict | None:
    """Parse one member line under object-group service or icmp-type group.

    Member dict type values are consumed by materialize_service_group_member.
    service-object object must be checked before generic service-object.
    Inline service-object lines are pre-parsed via parse_inline_service_object
    when possible; otherwise only raw is kept for normalizer retry.
    """
    low = stripped.lower()
    if low.startswith("group-object "):
        return {"type": "group-object", "name": stripped.split(maxsplit=1)[1].strip()}

    if low.startswith("service-object object "):
        name = stripped.split(maxsplit=2)[2].strip()
        return {"type": "service-object-object", "name": name}

    if low.startswith("service-object "):
        raw = stripped[len("service-object ") :].strip()
        parsed = parse_inline_service_object(raw)
        if parsed is None:
            return {"type": "service-object", "raw": raw}
        return {"type": "service-object", "payload": parsed, "raw": raw}

    if low.startswith("port-object "):
        raw = stripped[len("port-object ") :].strip()
        return {"type": "port-object", "raw": raw}

    if low.startswith("protocol-object "):
        raw = stripped[len("protocol-object ") :].strip()
        return {"type": "protocol-object", "raw": raw}

    return None


class ServiceExtractor:
    """Extract leaf services and service/icmp object-groups from config tree."""

    def extract(self, tree: ConfigTree, index: AsaIndex) -> ServiceExtractionResult:  # noqa: C901
        """Build ParsedServiceObject list from service-family index maps.

        Three passes over AsaIndex:

        1. object_service -> ParsedObjectType.SERVICE (leaf service lines)
        2. object_group_service -> ParsedObjectType.SERVICE_GROUP with header
           protocol token (e.g. object-group service WEB tcp -> protocol=tcp)
        3. object_group_icmp_type -> ParsedObjectType.SERVICE_GROUP with
           group_kind=icmp-type (same canonical kind, distinct trace fragment)

        Args:
            tree: Parsed configuration tree.
            index: Name->node index from AsaIndex.from_tree.

        Returns:
            Parsed services/groups with source_line on header nodes for trace.
        """
        results: list[ParsedServiceObject] = []

        for name, node_idx in index.object_service.items():
            node = tree.nodes[node_idx]
            source_span = tree.source_span(node_idx)
            payload: dict = {}

            for child in tree.children(node_idx):
                s = child.line.stripped
                if not s:
                    continue
                low = s.lower()
                if low.startswith("service "):
                    payload.update(_parse_service_line(s))
                elif low.startswith("description "):
                    payload["description"] = s.split(maxsplit=1)[1].strip()
                else:
                    payload.setdefault("raw_lines", []).append(s)

            results.append(
                ParsedServiceObject(
                    name=name,
                    kind=ParsedObjectType.SERVICE,
                    payload=payload,
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        for name, node_idx in index.object_group_service.items():
            node = tree.nodes[node_idx]
            source_span = tree.source_span(node_idx)
            header_parts = node.line.stripped.split()
            # Header form: object-group service NAME PROTO — PROTO drives port-object parsing.
            group_protocol = header_parts[3].lower() if len(header_parts) >= 4 else None
            group_payload: dict = {"members": [], "protocol": group_protocol}

            for child in tree.children(node_idx):
                s = child.line.stripped
                if not s:
                    continue
                low = s.lower()
                if low.startswith("description "):
                    group_payload["description"] = s.split(maxsplit=1)[1].strip()
                    continue
                member = _parse_service_group_member(s)
                if member is not None:
                    group_payload["members"].append(member)
                else:
                    group_payload.setdefault("raw_lines", []).append(s)

            results.append(
                ParsedServiceObject(
                    name=name,
                    kind=ParsedObjectType.SERVICE_GROUP,
                    payload=group_payload,
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        for name, node_idx in index.object_group_icmp_type.items():
            node = tree.nodes[node_idx]
            source_span = tree.source_span(node_idx)
            icmp_group_payload: dict = {
                "members": [],
                "protocol": "icmp",
                "group_kind": "icmp-type",
            }
            for child in tree.children(node_idx):
                s = child.line.stripped
                if not s:
                    continue
                low = s.lower()
                if low.startswith("description "):
                    icmp_group_payload["description"] = s.split(maxsplit=1)[1].strip()
                    continue
                if low.startswith("icmp-object "):
                    icmp_name = s.split(maxsplit=1)[1].strip()
                    icmp_group_payload["members"].append(
                        {"type": "icmp-object", "name": icmp_name}
                    )
                else:
                    icmp_group_payload.setdefault("raw_lines", []).append(s)

            results.append(
                ParsedServiceObject(
                    name=name,
                    kind=ParsedObjectType.SERVICE_GROUP,
                    payload=icmp_group_payload,
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        return ServiceExtractionResult(services=results)
