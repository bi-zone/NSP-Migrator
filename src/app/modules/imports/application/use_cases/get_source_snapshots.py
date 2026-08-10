"""Use case for listing recent source snapshots with display metadata."""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import SourceSnapshotListItemDTO
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class GetSourceSnapshotsQuery:
    """Query parameters for recent snapshots list."""
    limit: int = 200


@dataclass(slots=True)
class GetSourceSnapshotsResult:
    """Represent output payload returned by GetSourceSnapshots flow."""
    snapshots: list[SourceSnapshotListItemDTO]


class GetSourceSnapshotsUseCase:
    """Read-only use case enriching snapshots with source and file names."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetSourceSnapshotsQuery) -> GetSourceSnapshotsResult:
        """List recent snapshots with related source and file names.

        Simple in-memory caches are used to avoid repeated repository lookups.

        Args:
            query: Maximum number of snapshots to return.

        Returns:
            Snapshot list enriched with source and file names.
        """
        snapshots = await self.uow.snapshots.list_recent(limit=query.limit)
        sources_cache: dict[str, str] = {}
        file_names_cache: dict[str, str | None] = {}
        snapshot_dtos: list[SourceSnapshotListItemDTO] = []

        for snapshot in snapshots:
            source_name = None
            if snapshot.source_id is not None:
                source_id = str(snapshot.source_id)
                if source_id not in sources_cache:
                    source = await self.uow.sources.get_by_id(snapshot.source_id)
                    sources_cache[source_id] = (
                        source.name if source else "unknown-source"
                    )
                source_name = sources_cache[source_id]

            snapshot_id = str(snapshot.id)
            if snapshot_id not in file_names_cache:
                upload = await self.uow.uploads.get_latest_by_snapshot(snapshot.id)
                file_names_cache[snapshot_id] = upload.file_name if upload else None

            snapshot_dtos.append(
                SourceSnapshotListItemDTO(
                    id=snapshot.id,
                    source_id=snapshot.source_id,
                    source_name=source_name,
                    file_name=file_names_cache[snapshot_id],
                    artifact_hash=snapshot.artifact_hash,
                    source_format=snapshot.source_format,
                    is_latest=snapshot.is_latest,
                    created_at=snapshot.created_at,
                )
            )

        return GetSourceSnapshotsResult(snapshots=snapshot_dtos)
