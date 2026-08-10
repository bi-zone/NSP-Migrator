from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.parsed_config import (
    AclBindingType,
    ZoneInferenceStatus,
)
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree

_ACCESS_GROUP_RE = re.compile(
    r"^access-group\s+(?P<acl>\S+)\s+(?P<direction>in|out)\s+interface\s+(?P<iface>\S+)",
    re.IGNORECASE,
)

_ACCESS_GROUP_GLOBAL_RE = re.compile(
    r"^access-group\s+(?P<acl>\S+)\s+global\s*$",
    re.IGNORECASE,
)

_ACL_NAME_ZONE_RE = re.compile(
    r"^(?:ACL[_-])?(?P<src>[A-Z0-9]+)[_-]TO[_-](?P<dst>[A-Z0-9]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ZoneResolution:
    """One binding context for an ACL name.

    Copied onto ParsedAccessRule by ExtendedAclExtractor. Multiple
    resolutions per ACL line are expected when the ACL is bound to several
    interfaces (test_tc_08_multi_iface_different_zones).
    """

    src_zone: str | None
    dst_zone: str | None
    unresolved: bool
    binding_type: AclBindingType
    zone_inference_status: ZoneInferenceStatus
    binding_interface: str | None = None
    binding_direction: str | None = None
    binding_context_key: str = "unbound"


class ZoneResolver:
    """Infer zones from access-group bindings and ACL naming heuristics."""

    def __init__(
        self,
        *,
        iface_to_zone: dict[str, str],
        acl_to_iface: dict[str, list[tuple[str, str]]],
        acl_global: frozenset[str],
    ):
        self._iface_to_zone = iface_to_zone
        self._acl_to_iface = acl_to_iface
        self._acl_global = acl_global

    @classmethod
    def from_tree(cls, tree: ConfigTree, index: AsaIndex) -> ZoneResolver:
        """Build resolver from nameif map and access-group lines.

        Interface->zone names come from AsaIndex.interfaces_nameif (populated
        during index build from indented nameif under interface headers).
        Parses both access-group ACL in|out interface IFACE and
        access-group ACL global forms.

        Called from CiscoAsaParserAdapter.parse before ACL extraction.
        """
        iface_to_zone = {k: v for k, v in index.interfaces_nameif.items()}

        acl_to_iface: dict[str, list[tuple[str, str]]] = {}
        acl_global: set[str] = set()
        for node in tree.nodes:
            s = node.line.stripped
            m_global = _ACCESS_GROUP_GLOBAL_RE.match(s)
            if m_global:
                acl_global.add(m_global.group("acl"))
                continue
            m = _ACCESS_GROUP_RE.match(s)
            if not m:
                continue
            acl = m.group("acl")
            iface = m.group("iface")
            direction = m.group("direction").lower()
            acl_to_iface.setdefault(acl, []).append((iface, direction))

        return cls(
            iface_to_zone=iface_to_zone,
            acl_to_iface=acl_to_iface,
            acl_global=frozenset(acl_global),
        )

    @staticmethod
    def _infer_from_acl_name(acl_name: str) -> tuple[str | None, str | None]:
        """Heuristic fallback: INSIDE_TO_DMZ / ACL_INSIDE_TO_DMZ -> zones.

        Used when interface nameif is missing or as supplemental src/dst
        on interface-bound ACLs (test_tc_21_acl_name_zone_inference).
        """
        m = _ACL_NAME_ZONE_RE.match(acl_name)
        if not m:
            return None, None
        return m.group("src").lower(), m.group("dst").lower()

    def resolve(self, acl_name: str) -> ZoneResolution:
        """Return the first binding context for an ACL name.

        Prefer resolve_all when fan-out is required — this helper discards
        additional interface/global bindings after the first entry.
        """
        return self.resolve_all(acl_name)[0]

    def resolve_all(self, acl_name: str) -> list[ZoneResolution]:
        """Return all binding contexts for one ACL name.

        May yield multiple rows: global binding plus each interface binding are
        independent entries. Interface in maps traffic destination to the
        interface zone; out maps source to the interface zone. Name-based
        inference fills missing directional zone when nameif is absent.

        Fallback when no bindings match: name heuristic only, else unbound
        with unresolved=True (test_tc_05_acl_no_binding_unresolved).
        """
        results: list[ZoneResolution] = []

        if acl_name in self._acl_global:
            results.append(
                ZoneResolution(
                    src_zone=None,
                    dst_zone=None,
                    unresolved=False,
                    binding_type=AclBindingType.GLOBAL,
                    zone_inference_status=ZoneInferenceStatus.GLOBAL_SCOPE,
                    binding_context_key="global",
                )
            )

        inferred_src, inferred_dst = self._infer_from_acl_name(acl_name)

        for iface, direction in self._acl_to_iface.get(acl_name, []):
            src_zone: str | None = None
            dst_zone: str | None = None
            z = self._iface_to_zone.get(iface)
            if z:
                # ASA direction: "in" = traffic toward this interface's zone (dst).
                if direction == "in":
                    dst_zone = z
                else:
                    src_zone = z
            src_zone = src_zone or inferred_src
            dst_zone = dst_zone or inferred_dst

            results.append(
                ZoneResolution(
                    src_zone=src_zone,
                    dst_zone=dst_zone,
                    unresolved=not (src_zone or dst_zone),
                    binding_type=AclBindingType.INTERFACE,
                    zone_inference_status=ZoneInferenceStatus.DIRECTIONAL,
                    binding_interface=iface,
                    binding_direction=direction,
                    binding_context_key=f"interface:{iface}:{direction}",
                )
            )

        if results:
            return results

        if inferred_src or inferred_dst:
            return [
                ZoneResolution(
                    src_zone=inferred_src,
                    dst_zone=inferred_dst,
                    unresolved=False,
                    binding_type=AclBindingType.UNKNOWN,
                    zone_inference_status=ZoneInferenceStatus.DIRECTIONAL,
                    binding_context_key="inferred",
                )
            ]

        return [
            ZoneResolution(
                src_zone=None,
                dst_zone=None,
                unresolved=True,
                binding_type=AclBindingType.UNKNOWN,
                zone_inference_status=ZoneInferenceStatus.UNKNOWN,
                binding_context_key="unbound",
            )
        ]