from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedAddressObject,
    ParsedObjectType,
)
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree


@dataclass(slots=True)
class AddressExtractionResult:
    """Address objects extracted from indexed object network / group headers."""

    address_objects: list[ParsedAddressObject]


def _parse_object_network_children(children: list[str]) -> dict:
    """Parse indented body lines under object network NAME.

    Produces payload dicts consumed by _addr_object_from_payload during
    normalizer header materialization. Recognized types: host, subnet,
    range, fqdn. Unrecognized lines accumulate in raw_lines.
    """
    payload: dict = {}
    for line in children:
        low = line.lower()
        if low.startswith("host "):
            payload["type"] = "host"
            payload["ip"] = line.split(maxsplit=1)[1].strip()
        elif low.startswith("subnet "):
            parts = line.split()
            if len(parts) >= 3:
                payload["type"] = "subnet"
                payload["ip"] = parts[1]
                payload["mask"] = parts[2]
        elif low.startswith("range "):
            parts = line.split()
            if len(parts) >= 3:
                payload["type"] = "range"
                payload["start"] = parts[1]
                payload["end"] = parts[2]
        elif low.startswith("fqdn"):
            parts = line.split()
            payload["type"] = "fqdn"
            payload["name"] = parts[-1]
        elif low.startswith("description "):
            payload["description"] = line.split(maxsplit=1)[1].strip()
        else:
            payload.setdefault("raw_lines", []).append(line)
    return payload


def _parse_object_group_network_children(children: list[str]) -> dict:
    """Parse indented body lines under object-group network NAME.

    Member lines become dict entries in payload["members"]. Order of
    if branches matters: network-object object must precede the generic
    network-object subnet branch (see forensic notes in project docs).

    String ref normalization is deferred to normalize_address_group_members.
    """
    payload: dict = {"members": []}
    for line in children:
        low = line.lower()
        if low.startswith("network-object host "):
            ip = line.split(maxsplit=2)[2].strip()
            payload["members"].append({"type": "host", "ip": ip})
        elif low.startswith("network-object object "):
            name = line.split(maxsplit=2)[2].strip()
            payload["members"].append({"type": "object", "name": name})
        elif low.startswith("network-object "):
            parts = line.split()
            if len(parts) >= 3:
                payload["members"].append(
                    {"type": "subnet", "ip": parts[1], "mask": parts[2]}
                )
        elif low.startswith("group-object "):
            name = line.split(maxsplit=1)[1].strip()
            payload["members"].append({"type": "group", "name": name})
        elif low.startswith("description "):
            payload["description"] = line.split(maxsplit=1)[1].strip()
        else:
            payload.setdefault("raw_lines", []).append(line)
    return payload


class AddressExtractor:
    """Extract address objects and network groups from config tree + index."""

    def extract(self, tree: ConfigTree, index: AsaIndex) -> AddressExtractionResult:
        """Build ParsedAddressObject list from indexed object headers.

        Uses AsaIndex.object_network and object_group_network to locate
        header nodes, then reads indented children via tree.children.

        Args:
            tree: Parsed configuration tree.
            index: Name->node index from AsaIndex.from_tree.

        Returns:
            Combined leaf objects and address groups with source_line set
            to the header line number (used for trace in normalizer).
        """
        results: list[ParsedAddressObject] = []

        for name, node_indices in index.object_network.items():
            declarations = [
                (
                    node_idx,
                    _parse_object_network_children(
                        [c.line.stripped for c in tree.children(node_idx)]
                    ),
                )
                for node_idx in node_indices
            ]
            node_idx, payload = next(
                (
                    declaration
                    for declaration in reversed(declarations)
                    if declaration[1].get("type") is not None
                ),
                declarations[-1],
            )
            source_span = tree.source_span(node_idx)
            results.append(
                ParsedAddressObject(
                    name=name,
                    kind=ParsedObjectType.ADDRESS,
                    payload=payload,
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        for name, node_idx in index.object_group_network.items():
            source_span = tree.source_span(node_idx)
            children = [c.line.stripped for c in tree.children(node_idx)]
            results.append(
                ParsedAddressObject(
                    name=name,
                    kind=ParsedObjectType.ADDRESS_GROUP,
                    payload=_parse_object_group_network_children(children),
                    source_line=source_span.line_start,
                    source_line_end=source_span.line_end,
                    source_fragment=source_span.fragment,
                )
            )

        return AddressExtractionResult(address_objects=results)
