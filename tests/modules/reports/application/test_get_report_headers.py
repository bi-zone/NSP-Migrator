from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.querying import Pagination, SortDirection, Sorting
from app.modules.reports.application.dto import (
    PaginationDTO,
    ReportHeaderDTO,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersQuery,
    GetReportHeadersUseCase,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.value_objects import ReportEnvironmentSnapshot
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
    ReportHeadersPage,
)


class _ReportsRepository:
    def __init__(self, page: ReportHeadersPage) -> None:
        self.page = page
        self.calls: list[tuple[Pagination, ReportHeaderFilters, Sorting]] = []

    async def list_report_headers(
        self,
        pagination: Pagination,
        *,
        filters: ReportHeaderFilters,
        sorting: Sorting,
    ) -> ReportHeadersPage:
        self.calls.append((pagination, filters, sorting))
        return self.page


class _Uow:
    def __init__(self, reports: _ReportsRepository) -> None:
        self.session = None
        self.reports = reports
        self.commits = 0

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    def __call__(self, reuse_session: bool = False) -> _Uow:
        return self

    async def commit(self) -> None:
        self.commits += 1


class _CSPProfileHeadersReader:
    def __init__(self, headers: tuple[CSPProfileHeaderDTO, ...]) -> None:
        self.headers = headers
        self.calls: list[tuple[UUID, ...]] = []

    async def get_headers_by_ids(
        self,
        profile_ids: tuple[UUID, ...],
    ) -> tuple[CSPProfileHeaderDTO, ...]:
        self.calls.append(profile_ids)
        return tuple(header for header in self.headers if header.id in profile_ids)


def _report(
    *,
    report_id: UUID | None = None,
    profile_id: UUID | None = None,
) -> Report:
    return Report(
        id=report_id or uuid4(),
        title="Branch migration — 14.09.2026-10:00:00",
        created_at=datetime(2026, 9, 14, 10, tzinfo=UTC),
        csp_profile_id=profile_id or uuid4(),
        commit_id=42,
        environment=ReportEnvironmentSnapshot(
            project_name="Firewall migration",
            vpc_id="vpc-1",
            target_name="Branch gateway",
            target_id="target-1",
        ),
    )


@pytest.mark.asyncio
async def test_get_report_headers_forwards_query_and_projects_header_data() -> None:
    report_id = uuid4()
    profile_id = uuid4()
    report = _report(report_id=report_id, profile_id=profile_id)
    repository = _ReportsRepository(ReportHeadersPage(reports=(report,), total=3))
    profile_headers_reader = _CSPProfileHeadersReader(
        (CSPProfileHeaderDTO(id=profile_id, name="Production", base_url="https://example.com"),)
    )
    use_case = GetReportHeadersUseCase(  # type: ignore[arg-type]
        _Uow(repository),
        profile_headers_reader,
    )
    filters = ReportHeaderFilters(
        search_by_name="branch",
        created_from=datetime(2026, 9, 1, tzinfo=UTC).date(),
        created_to=datetime(2026, 9, 14, tzinfo=UTC).date(),
        csp_profile_id=profile_id,
        vpc_id="vpc-1",
        target_ids=("target-1", "target-2"),
    )
    pagination = Pagination(limit=25, offset=50)
    sorting = Sorting(
        field=ReportHeaderSortField.CREATED_AT,
        direction=SortDirection.ASC,
    )

    result = await use_case.execute(
        GetReportHeadersQuery(
            filters=filters,
            pagination=pagination,
            sorting=sorting,
        )
    )

    assert repository.calls == [(pagination, filters, sorting)]
    assert profile_headers_reader.calls == [(profile_id,)]
    assert result.pagination.limit == 25
    assert result.pagination.offset == 50
    assert result.pagination.total == 3
    assert result.reports == [
        ReportHeaderDTO(
            id=report_id,
            title="Branch migration — 14.09.2026-10:00:00",
            csp_profile=CSPProfileHeaderDTO(
                id=profile_id,
                name="Production",
                base_url="https://example.com",
            ),
            project_name="Firewall migration",
            vpc_id="vpc-1",
            target_name="Branch gateway",
            target_id="target-1",
            created_at=datetime(2026, 9, 14, 10, tzinfo=UTC),
        )
    ]


@pytest.mark.asyncio
async def test_get_report_headers_uses_newest_first_defaults() -> None:
    repository = _ReportsRepository(ReportHeadersPage(reports=(), total=0))
    profile_headers_reader = _CSPProfileHeadersReader(())
    use_case = GetReportHeadersUseCase(  # type: ignore[arg-type]
        _Uow(repository),
        profile_headers_reader,
    )

    result = await use_case.execute(GetReportHeadersQuery())

    assert result.reports == []
    assert result.pagination == PaginationDTO(limit=None, offset=0, total=0)
    assert profile_headers_reader.calls == []
    _, filters, sorting = repository.calls[0]
    assert filters == ReportHeaderFilters()
    assert sorting.field == ReportHeaderSortField.CREATED_AT
    assert sorting.direction == SortDirection.DESC
