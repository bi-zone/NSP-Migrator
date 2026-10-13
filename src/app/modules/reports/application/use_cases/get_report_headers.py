"""List immutable migration-report headers."""

from dataclasses import dataclass, field
from uuid import UUID

from app.core.querying import Pagination, Sorting
from app.infrastructure.db.transactional import async_transactional
from app.modules.reports.application.dto import PaginationDTO, ReportHeaderDTO
from app.modules.reports.application.mappers import report_to_header_dto
from app.modules.reports.ports.csp_profile_headers_reader import (
    CSPProfileHeaderDTO,
    CSPProfileHeadersReaderPort,
)
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
    ReportHeadersPage,
    default_report_header_sorting,
)
from app.modules.reports.ports.uow import ReportsUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class GetReportHeadersQuery:
    """Filters, page, and order for report-header history."""

    filters: ReportHeaderFilters = field(default_factory=ReportHeaderFilters)
    sorting: Sorting[ReportHeaderSortField] = field(
        default_factory=default_report_header_sorting
    )
    pagination: Pagination = field(default_factory=Pagination)


@dataclass(frozen=True, slots=True)
class GetReportHeadersResult:
    reports: list[ReportHeaderDTO]
    pagination: PaginationDTO


class GetReportHeadersUseCase:
    """Read filtered report snapshots without loading policy outcomes."""

    def __init__(
        self,
        uow: ReportsUnitOfWorkPort,
        csp_profile_headers_reader: CSPProfileHeadersReaderPort,
    ) -> None:
        self.uow = uow
        self._csp_profile_headers_reader = csp_profile_headers_reader

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GetReportHeadersQuery,
    ) -> GetReportHeadersResult:
        # -- retrieve list of reports headers
        page: ReportHeadersPage = await self.uow.reports.list_report_headers(
            query.pagination,
            filters=query.filters,
            sorting=query.sorting,
        )
        # -- get csp profiles data for linked profile_ids of reports list
        profile_ids: tuple[UUID, ...] = tuple(
            set(report.csp_profile_id for report in page.reports)
        )
        profile_headers_by_id: dict[UUID, CSPProfileHeaderDTO] = {}
        if profile_ids:
            profile_headers = await self._csp_profile_headers_reader.get_headers_by_ids(
                profile_ids
            )
            profile_headers_by_id = {header.id: header for header in profile_headers}
        # -- return reports headers with csp profile header data
        return GetReportHeadersResult(
            reports=[
                report_to_header_dto(
                    report=report,
                    csp_profile=profile_headers_by_id[report.csp_profile_id],
                )
                for report in page.reports
            ],
            pagination=PaginationDTO(
                limit=query.pagination.limit,
                offset=query.pagination.offset,
                total=page.total,
            ),
        )
