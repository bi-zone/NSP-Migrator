from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotResult,
    SaveCanonicalSnapshotUseCase,
)
from app.modules.imports.cisco_asa.ports.normalizer import CiscoAsaNormalizerPort
from app.modules.imports.cisco_asa.ports.parser import CiscoAsaParserPort
from app.modules.imports.errors import SourceArtifactNotFoundError
from app.modules.imports.ports.uow import ImportsUoWPort
from app.modules.trace.application.dto import SaveTraceRecordsCommand
from app.modules.trace.application.use_cases.save_trace_records import (
    SaveTraceRecordsUseCase,
)


@dataclass(slots=True)
class RunCiscoMappingCommand:
    """Identify source snapshot to map into canonical + trace storage.

    Attributes:
        source_snapshot_id: Snapshot whose source_artifact row provides
            raw_text for parsing.
    """

    source_snapshot_id: UUID


@dataclass(slots=True)
class RunCiscoMappingResult:
    """Outcome of one map-to-canonical invocation.

    Attributes:
        canonical_snapshot_id: Existing or newly created canonical snapshot for
            this source snapshot + normalizer identity.
        trace_records_written: Count of trace rows persisted. 0 when
            canonical save was idempotent (created=False).
    """

    canonical_snapshot_id: UUID
    trace_records_written: int


class RunCiscoMappingUseCase:
    """Orchestrate parsing, normalization, canonical save, and trace write.

    Composes imports, canonical, and trace application use cases. Wired in
    cisco_asa/di/container.py with parser/normalizer singletons and
    cross-module save use cases.

    Idempotency is delegated to SaveCanonicalSnapshotUseCase: when a SUCCESS
    snapshot already exists for (source_snapshot_id, normalizer_code,
    normalizer_version), trace persistence is skipped to avoid duplicate
    lineage rows (see test_mapping_use_case_reuses_existing_snapshot_without_trace_rewrite).
    """

    def __init__(
        self,
        uow: ImportsUoWPort,
        *,
        parser: CiscoAsaParserPort,
        normalizer: CiscoAsaNormalizerPort,
        save_canonical_snapshot: SaveCanonicalSnapshotUseCase,
        save_trace_records: SaveTraceRecordsUseCase,
    ) -> None:
        self.uow = uow
        self._parser = parser
        self._normalizer = normalizer
        self._save_canonical_snapshot = save_canonical_snapshot
        self._save_trace_records = save_trace_records

    @async_transactional(
        uc_for_reuse_session=["_save_canonical_snapshot", "_save_trace_records"],
    )
    async def execute(self, command: RunCiscoMappingCommand) -> RunCiscoMappingResult:
        """Run parse->normalize->save pipeline for one source snapshot.

        Transaction spans artifact read, in-memory parse/normalize, and nested
        canonical/trace writes (shared DB session via uc_for_reuse_session).

        Args:
            command: Snapshot identifier to map into canonical model.

        Returns:
            Canonical snapshot id and number of trace rows written on fresh
            create. Repeat calls return the same snapshot id with
            trace_records_written=0.

        Raises:
            SourceArtifactNotFoundError: When no raw artifact exists — HTTP
                router maps this to 404 in map_snapshot_to_canonical.

        Side Effects:
            On first successful map: inserts canonical entities and trace
            records. On idempotent hit: no trace rewrite.
        """
        artifact = await self.uow.artifacts.get_by_snapshot_id(
            command.source_snapshot_id
        )
        if not artifact:
            raise SourceArtifactNotFoundError(
                f"source_artifact not found for snapshot_id={command.source_snapshot_id}"
            )

        parsed = self._parser.parse(artifact.raw_text)
        outcome = self._normalizer.normalize(
            parsed,
            source_snapshot_id=command.source_snapshot_id,
        )

        saved: SaveCanonicalSnapshotResult = (
            await self._save_canonical_snapshot.execute(outcome.canonical)
        )
        if not saved.created:
            # Idempotent hit — existing canonical snapshot; do not append trace rows again.
            return RunCiscoMappingResult(
                canonical_snapshot_id=saved.canonical_snapshot_id,
                trace_records_written=0,
            )

        # Normalizer uses provisional UUIDs; rebind trace rows to persisted snapshot id.
        rebound = [
            r.with_canonical_snapshot_id(saved.canonical_snapshot_id)
            for r in outcome.trace.records
        ]
        trace_result = await self._save_trace_records.execute(
            SaveTraceRecordsCommand(records=rebound)
        )

        return RunCiscoMappingResult(
            canonical_snapshot_id=saved.canonical_snapshot_id,
            trace_records_written=trace_result.written,
        )