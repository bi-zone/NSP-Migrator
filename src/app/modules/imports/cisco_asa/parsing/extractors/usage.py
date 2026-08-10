from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.cisco_asa.domain.enums import AclUsageType
from app.modules.imports.cisco_asa.domain.parsed_config import CryptoMapLink
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.tree import ConfigTree


@dataclass(frozen=True, slots=True)
class AclUsageResolution:
    """Usage classification for one ACL name.

    Attached to ParsedAccessRule fields acl_usage_type,
    crypto_map_name, and crypto_map_seq by ExtendedAclExtractor.
    """

    usage_type: AclUsageType
    crypto_map_name: str | None = None
    crypto_map_seq: int | None = None
    crypto_map_source_line: int | None = None


class AclUsageClassifier:
    """Resolve firewall vs crypto-map usage for ACL names during parse."""

    def __init__(
        self,
        *,
        firewall_acls: frozenset[str],
        crypto_map_by_acl: dict[str, list[CryptoMapLink]],
    ) -> None:
        self._firewall_acls = firewall_acls
        self._crypto_map_by_acl = crypto_map_by_acl

    @classmethod
    def from_tree(cls, tree: ConfigTree, index: AsaIndex) -> AclUsageClassifier:
        """Build classifier from access-group lines and index crypto-map links.

        Firewall ACL names are collected by scanning all tree nodes for
        access-group <ACL> …. Crypto-map bindings come from
        AsaIndex.crypto_map_by_acl (populated during AsaIndex.from_tree).

        Called from CiscoAsaParserAdapter.parse before ACL extraction.
        """
        firewall_acls: set[str] = set()
        for node in tree.nodes:
            s = node.line.stripped.lower()
            if s.startswith("access-group "):
                parts = node.line.stripped.split()
                if len(parts) >= 2:
                    firewall_acls.add(parts[1])
        return cls(
            firewall_acls=frozenset(firewall_acls),
            crypto_map_by_acl=index.crypto_map_by_acl,
        )

    def resolve(self, acl_name: str) -> AclUsageResolution:
        """Classify one ACL by firewall and crypto-map references.

        Resolution priority (first match wins):

        1. Both access-group and crypto map -> CONFLICT
        2. Crypto map only -> CRYPTO_MAP_SELECTOR
        3. Firewall access-group only -> FIREWALL_POLICY
        4. Neither -> UNKNOWN

        When crypto links exist, metadata from the first link in
        crypto_map_by_acl[acl_name] is returned. Issue codes
        usage_conflict and crypto_map_selector depend on these enum
        values — keep stable for test_rule_issue_codes regressions.
        """
        crypto_links = self._crypto_map_by_acl.get(acl_name, [])
        is_firewall = acl_name in self._firewall_acls
        is_crypto = bool(crypto_links)

        if is_firewall and is_crypto:
            link = crypto_links[0]
            return AclUsageResolution(
                usage_type=AclUsageType.CONFLICT,
                crypto_map_name=link.map_name,
                crypto_map_seq=link.sequence,
                crypto_map_source_line=link.source_line,
            )

        if is_crypto:
            link = crypto_links[0]
            return AclUsageResolution(
                usage_type=AclUsageType.CRYPTO_MAP_SELECTOR,
                crypto_map_name=link.map_name,
                crypto_map_seq=link.sequence,
                crypto_map_source_line=link.source_line,
            )

        if is_firewall:
            return AclUsageResolution(usage_type=AclUsageType.FIREWALL_POLICY)

        if crypto_links:
            link = crypto_links[0]
            return AclUsageResolution(
                usage_type=AclUsageType.CRYPTO_MAP_SELECTOR,
                crypto_map_name=link.map_name,
                crypto_map_seq=link.sequence,
                crypto_map_source_line=link.source_line,
            )

        return AclUsageResolution(usage_type=AclUsageType.UNKNOWN)