"""Normalizer port for Cisco ASA parsed data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotCommand,
)
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig
from app.modules.trace.application.dto import SaveTraceRecordsCommand


@dataclass(slots=True)
class NormalizeOutcome:
    """Aggregate of canonical snapshot and trace commands produced by normalization."""

    canonical: SaveCanonicalSnapshotCommand
    trace: SaveTraceRecordsCommand


class CiscoAsaNormalizerPort(Protocol):
    """Port defining parsed-config to canonical/trace normalization contract."""

    def normalizer_identity(self) -> tuple[str, str]:
        """Return stable normalizer identity tuple used in produced metadata.

        Returns:
            Pair (code, version) embedded into canonical and trace metadata.
        """
        ...

    def normalize(
        self,
        parsed: ParsedConfig,
        *,
        source_snapshot_id: UUID,
    ) -> NormalizeOutcome:
        """Transform parsed Cisco ASA data into canonical snapshot and trace commands.

        Args:
            parsed: Parsed Cisco ASA configuration produced by parser adapter.
            source_snapshot_id: Identifier of the source snapshot.

        Returns:
            Container with canonical snapshot command and trace records command.
        """
        ...
