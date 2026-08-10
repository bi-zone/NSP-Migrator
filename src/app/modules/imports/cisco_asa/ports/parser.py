"""Parser port for Cisco ASA raw configuration text."""

from __future__ import annotations

from typing import Protocol

from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig


class CiscoAsaParserPort(Protocol):
    """Port defining parser capability for Cisco ASA imports."""

    def parse(self, raw_text: str) -> ParsedConfig:
        """Parse raw Cisco ASA configuration text into ParsedConfig structure.

        Args:
            raw_text: Raw uploaded configuration text.

        Returns:
            Parsed Cisco ASA configuration model ready for normalization.
        """
        ...
