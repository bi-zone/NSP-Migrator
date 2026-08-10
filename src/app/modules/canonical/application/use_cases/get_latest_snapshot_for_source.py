"""Resolve the latest canonical snapshot for an imports source snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalSnapshotDTO
from app.modules.canonical.application.mappers import snapshot_to_dto
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetLatestCanonicalSnapshotForSourceQuery:
    """Input: imports source snapshot identifier."""

    source_snapshot_id: UUID


@dataclass(slots=True)
class GetLatestCanonicalSnapshotForSourceResult:
    """Nullable result when no canonical snapshot exists yet for the source."""

    snapshot: CanonicalSnapshotDTO | None


class GetLatestCanonicalSnapshotForSourceUseCase:
    """Find the most recent canonical snapshot for an imports source snapshot.

    Returns snapshot=None instead of raising when no canonical row exists.
    Used internally during imports/mapping orchestration.
    """

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self, query: GetLatestCanonicalSnapshotForSourceQuery
    ) -> GetLatestCanonicalSnapshotForSourceResult:
        snapshot = await self.uow.snapshots.get_latest_for_source(
            query.source_snapshot_id
        )
        if snapshot is None:
            return GetLatestCanonicalSnapshotForSourceResult(snapshot=None)
        return GetLatestCanonicalSnapshotForSourceResult(
            snapshot=snapshot_to_dto(snapshot)
        )
