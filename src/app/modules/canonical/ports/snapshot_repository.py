from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.canonical.domain.enums import SnapshotStatus
from app.modules.canonical.domain.issue import CanonicalIssue
from app.modules.canonical.domain.snapshot import CanonicalSnapshot


class CanonicalSnapshotRepositoryPort(IAsyncRepository[CanonicalSnapshot, UUID]):
    """Snapshot lifecycle: save, idempotent lookup, counts, issues."""

    @abstractmethod
    async def save(self, snapshot: CanonicalSnapshot) -> None: ...

    @abstractmethod
    async def save_issues(self, issues: list[CanonicalIssue]) -> None: ...

    @abstractmethod
    async def update_counts(
        self,
        *,
        snapshot_id: UUID,
        zones_total: int,
        objects_total: int,
        rules_total: int,
        issues_total: int,
    ) -> None: ...

    @abstractmethod
    async def update_status(
        self, snapshot_id: UUID, status: SnapshotStatus
    ) -> None: ...

    @abstractmethod
    async def get_by_id(self, snapshot_id: UUID) -> CanonicalSnapshot | None: ...

    @abstractmethod
    async def get_latest_for_source(
        self, source_snapshot_id: UUID
    ) -> CanonicalSnapshot | None: ...

    @abstractmethod
    async def get_by_source_and_normalizer(
        self,
        *,
        source_snapshot_id: UUID,
        normalizer_code: str,
        normalizer_version: str,
    ) -> CanonicalSnapshot | None: ...

    @abstractmethod
    async def get_issues_by_snapshot(
        self, snapshot_id: UUID
    ) -> list[CanonicalIssue]: ...
