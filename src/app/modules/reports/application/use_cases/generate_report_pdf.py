"""Generate a PDF export for one complete saved migration report."""

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.reports.application.services.report_pdf_builder import ReportPdfBuilder
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.ports.csp_profile_headers_reader import (
    CSPProfileHeadersReaderPort,
)
from app.modules.reports.ports.uow import ReportsUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class GenerateReportPdfQuery:
    """Identifier of the immutable report to export."""

    report_id: UUID


@dataclass(frozen=True, slots=True)
class GenerateReportPdfResult:
    """Generated PDF document bytes for a report download."""

    content: bytes


class GenerateReportPdfUseCase:
    """Build a complete PDF without using UI filters or remote SD-WAN data."""

    def __init__(
        self,
        uow: ReportsUnitOfWorkPort,
        csp_profile_headers_reader: CSPProfileHeadersReaderPort,
        pdf_builder: ReportPdfBuilder,
    ) -> None:
        self.uow = uow
        self._csp_profile_headers_reader = csp_profile_headers_reader
        self._pdf_builder = pdf_builder

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GenerateReportPdfQuery,
    ) -> GenerateReportPdfResult:
        report = await self.uow.reports.get_report_by_id(query.report_id)
        if report is None:
            raise ReportsModuleNotFoundError(f"Report {query.report_id} not found")

        csp_profile = await self._csp_profile_headers_reader.get_header_by_id(
            report.csp_profile_id
        )
        return GenerateReportPdfResult(
            content=self._pdf_builder.build(
                report=report,
                csp_profile=csp_profile,
            )
        )
