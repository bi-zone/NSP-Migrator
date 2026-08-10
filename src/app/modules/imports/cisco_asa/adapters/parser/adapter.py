from __future__ import annotations

from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig
from app.modules.imports.cisco_asa.parsing.address_group_members import (
    normalize_address_group_members,
)
from app.modules.imports.cisco_asa.parsing.extractors.acls import ExtendedAclExtractor
from app.modules.imports.cisco_asa.parsing.extractors.addresses import AddressExtractor
from app.modules.imports.cisco_asa.parsing.extractors.protocol_groups import (
    ProtocolGroupExtractor,
)
from app.modules.imports.cisco_asa.parsing.extractors.services import ServiceExtractor
from app.modules.imports.cisco_asa.parsing.extractors.usage import AclUsageClassifier
from app.modules.imports.cisco_asa.parsing.extractors.zones import ZoneResolver
from app.modules.imports.cisco_asa.parsing.index import AsaIndex
from app.modules.imports.cisco_asa.parsing.tree import ConfigTreeBuilder
from app.modules.imports.errors import DomainValidationError


class CiscoAsaParserAdapter:
    """Adapter that parses raw ASA text into internal parsed config model."""

    def parse(self, raw_text: str) -> ParsedConfig:
        """Parse raw Cisco ASA configuration text into ParsedConfig structure.

        Args:
            raw_text: Raw uploaded configuration text.

        Returns:
            Parsed Cisco ASA configuration model ready for normalization.
        """
        if not raw_text.strip():
            raise DomainValidationError("Cisco ASA config is empty")

        tree = ConfigTreeBuilder().build(raw_text)
        index = AsaIndex.from_tree(tree)
        zones = ZoneResolver.from_tree(tree, index)
        usage = AclUsageClassifier.from_tree(tree, index)

        addresses = AddressExtractor().extract(tree, index)
        services = ServiceExtractor().extract(tree, index)
        protocol_groups = ProtocolGroupExtractor().extract(tree, index)
        acls = ExtendedAclExtractor().extract(tree, zones=zones, usage=usage)

        parsed = ParsedConfig(
            address_objects=addresses.address_objects,
            service_objects=[*services.services, *protocol_groups.protocol_groups],
            rules=acls.rules,
            crypto_map_links=[
                link for links in index.crypto_map_by_acl.values() for link in links
            ],
        )
        normalize_address_group_members(parsed)

        if not parsed.rules:
            raise DomainValidationError("No ACL rules found in Cisco ASA config")
        return parsed
