from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig
from app.modules.imports.cisco_asa.ports.parser import CiscoAsaParserPort
from app.modules.imports.errors import SourceArtifactNotFoundError
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class RunCiscoImportCommand:
    """Identify which uploaded source snapshot to parse.

    Attributes:
        source_snapshot_id: Primary key of the snapshot whose raw artifact
            should be loaded from imports storage.
    """

    source_snapshot_id: UUID


@dataclass(slots=True)
class RunCiscoImportResult:
    """Parser output for one snapshot — not persisted by this use case.

    Attributes:
        parsed: In-memory ASA configuration tree (rules, objects, bindings)
            consumed by the normalizer or inspection tooling.
    """

    parsed: ParsedConfig


class RunCiscoImportUseCase:
    """Load artifact from DB and parse Cisco ASA configuration text.

    Read-only application orchestration: touches ImportsUoWPort.artifacts
    for load and CiscoAsaParserPort for CPU-bound parsing. Does not write
    canonical or trace data.

    RunCiscoMappingUseCase currently inlines the same load+parse steps
    rather than delegating here — both paths must stay behavior-compatible if
    refactored to compose later.
    """

    def __init__(self, uow: ImportsUoWPort, *, parser: CiscoAsaParserPort) -> None:
        self.uow = uow
        self._parser = parser

    @async_transactional(read_only=True)
    async def execute(self, command: RunCiscoImportCommand) -> RunCiscoImportResult:
        """Load raw snapshot artifact and parse it with Cisco ASA parser.

        Transaction boundary is read-only — suitable for parse-only inspection
        endpoints or pre-normalize validation without side effects.

        Args:
            command: Snapshot identifier to parse.

        Returns:
            Parsed configuration tree; next step in full pipeline is
            CiscoAsaNormalizerPort.normalize(parsed, ...).

        Raises:
            SourceArtifactNotFoundError: When no artifact row exists for
                command.source_snapshot_id (HTTP layer maps this to 404 in
                run_cisco_mapping router pattern).
        """
        artifact = await self.uow.artifacts.get_by_snapshot_id(
            command.source_snapshot_id
        )
        if not artifact:
            raise SourceArtifactNotFoundError(
                f"source_artifact not found for snapshot_id={command.source_snapshot_id}"
            )
        parsed = self._parser.parse(artifact.raw_text)
        return RunCiscoImportResult(parsed=parsed)