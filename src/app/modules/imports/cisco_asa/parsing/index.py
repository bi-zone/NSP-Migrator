from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.parsed_config import CryptoMapLink
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree

_CRYPTO_MAP_MATCH_RE = re.compile(
    r"^crypto\s+map\s+(?P<map>\S+)\s+(?P<seq>\d+)\s+match\s+address\s+(?P<acl>\S+)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AsaIndex:
    """Name->node index built from a parsed ASA config tree.

    Dict values identify ConfigNode.idx positions in tree.nodes. Network
    objects keep a list of positions; the remaining maps keep one position.
    Extractors use these indices to read object bodies.

    Repeated object network declarations are preserved because ASA configs may
    reopen an existing network object to attach NAT settings in a separate
    stanza. Other duplicate object headers retain last-header-wins semantics.

    Attributes:
        object_network: object network NAME headers.
        object_group_network: object-group network NAME headers.
        object_service: object service NAME headers.
        object_group_service: object-group service NAME headers.
        object_group_icmp_type: object-group icmp-type NAME headers.
        object_group_protocol: object-group protocol NAME headers.
        interfaces_nameif: ASA interface name -> nameif zone label.
        crypto_map_by_acl: ACL name -> crypto-map match address links
            (supports multiple links per ACL).
    """

    object_network: dict[str, list[int]]
    object_group_network: dict[str, int]
    object_service: dict[str, int]
    object_group_service: dict[str, int]
    object_group_icmp_type: dict[str, int]
    object_group_protocol: dict[str, int]
    interfaces_nameif: dict[str, str]
    crypto_map_by_acl: dict[str, list[CryptoMapLink]]

    @classmethod
    def from_tree(cls, tree: ConfigTree) -> AsaIndex:  # noqa: C901
        """Scan config tree once and populate all index maps.

        Tracks current_interface while walking nodes so indented nameif
        lines attach to the most recent interface header.

        Side Effects:
            None — returns a new AsaIndex instance.
        """
        object_network: dict[str, list[int]] = {}
        object_group_network: dict[str, int] = {}
        object_service: dict[str, int] = {}
        object_group_service: dict[str, int] = {}
        object_group_icmp_type: dict[str, int] = {}
        object_group_protocol: dict[str, int] = {}
        interfaces_nameif: dict[str, str] = {}
        crypto_map_by_acl: dict[str, list[CryptoMapLink]] = {}

        current_interface: str | None = None

        for node in tree.nodes:
            s = node.line.stripped
            low = s.lower()

            if low.startswith("interface "):
                current_interface = s.split(maxsplit=1)[1].strip()
                continue

            if current_interface and node.line.indent > 0 and low.startswith("nameif "):
                interfaces_nameif[current_interface] = s.split(maxsplit=1)[1].strip()
                continue

            if low.startswith("object network "):
                name = s.split(maxsplit=2)[2].strip()
                object_network.setdefault(name, []).append(node.idx)
                continue

            if low.startswith("object-group network "):
                parts = s.split()
                if len(parts) >= 3:
                    name = parts[2].strip()
                    object_group_network[name] = node.idx
                continue

            if low.startswith("object service "):
                name = s.split(maxsplit=2)[2].strip()
                object_service[name] = node.idx
                continue

            if low.startswith("object-group service "):
                parts = s.split()
                if len(parts) >= 3:
                    name = parts[2].strip()
                    object_group_service[name] = node.idx
                continue

            if low.startswith("object-group icmp-type "):
                name = s.split(maxsplit=2)[2].strip()
                object_group_icmp_type[name] = node.idx
                continue

            if low.startswith("object-group protocol "):
                name = s.split(maxsplit=2)[2].strip()
                object_group_protocol[name] = node.idx
                continue

            m_crypto = _CRYPTO_MAP_MATCH_RE.match(s)
            if m_crypto:
                link = CryptoMapLink(
                    map_name=m_crypto.group("map"),
                    sequence=int(m_crypto.group("seq")),
                    acl_name=m_crypto.group("acl"),
                    source_line=node.line.line_no,
                )
                crypto_map_by_acl.setdefault(link.acl_name, []).append(link)
                continue

        return cls(
            object_network=object_network,
            object_group_network=object_group_network,
            object_service=object_service,
            object_group_service=object_group_service,
            object_group_icmp_type=object_group_icmp_type,
            object_group_protocol=object_group_protocol,
            interfaces_nameif=interfaces_nameif,
            crypto_map_by_acl=crypto_map_by_acl,
        )
