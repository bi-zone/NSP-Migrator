"""List normalizer issues for a snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalIssueDTO
from app.modules.canonical.application.mappers import issue_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalIssuesQuery:
    canonical_snapshot_id: UUID


@dataclass(slots=True)
class GetCanonicalIssuesResult:
    issues: list[CanonicalIssueDTO]


class GetCanonicalIssuesUseCase:
    """Read issues recorded during snapshot materialization."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalIssuesQuery) -> GetCanonicalIssuesResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        issues = await self.uow.snapshots.get_issues_by_snapshot(
            query.canonical_snapshot_id
        )
        return GetCanonicalIssuesResult(issues=[issue_to_dto(i) for i in issues])
