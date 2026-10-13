from collections.abc import Callable
from uuid import UUID

import pytest

from app.modules.reports.adapters.db.uow import ReportsUnitOfWork
from app.modules.reports.application.services.report_pdf_builder import ReportPdfBuilder
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfQuery,
    GenerateReportPdfUseCase,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


class _CSPProfileHeadersReader:
    def __init__(self, header: CSPProfileHeaderDTO) -> None:
        self.header = header
        self.calls: list[UUID] = []

    async def get_header_by_id(self, profile_id: UUID) -> CSPProfileHeaderDTO:
        self.calls.append(profile_id)
        return self.header


class _CapturingPdfBuilder:
    def __init__(self) -> None:
        self._delegate = ReportPdfBuilder()
        self.calls: list[tuple[Report, CSPProfileHeaderDTO]] = []

    def build(self, *, report: Report, csp_profile: CSPProfileHeaderDTO) -> bytes:
        self.calls.append((report, csp_profile))
        return self._delegate.build(report=report, csp_profile=csp_profile)


@pytest.mark.asyncio
async def test_generate_report_pdf_uses_complete_snapshot_of_requested_report(
    csp_profile_id: UUID,
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    requested_report = report_factory(priorities=(20, 10))
    unrelated_report = report_factory(priorities=(40, 30))
    async with reports_uow_factory() as uow:
        await uow.reports.save_report(requested_report)
        await uow.reports.save_report(unrelated_report)
        await uow.commit()

    profile_header = CSPProfileHeaderDTO(
        id=csp_profile_id,
        name="Production",
        base_url="https://sdwan.example.test",
    )
    profile_reader = _CSPProfileHeadersReader(profile_header)
    pdf_builder = _CapturingPdfBuilder()
    use_case = GenerateReportPdfUseCase(
        reports_uow_factory(),
        profile_reader,  # type: ignore[arg-type]
        pdf_builder,  # type: ignore[arg-type]
    )

    result = await use_case.execute(
        GenerateReportPdfQuery(report_id=requested_report.id)
    )

    assert result.content
    assert profile_reader.calls == [csp_profile_id]
    assert len(pdf_builder.calls) == 1
    report, captured_profile_header = pdf_builder.calls[0]
    assert report.id == requested_report.id
    assert report.id != unrelated_report.id
    assert report.rules is not None
    assert [rule.policy_name for rule in report.rules] == ["policy-10", "policy-20"]
    assert [rule.priority for rule in report.rules] == [10, 20]
    assert captured_profile_header == profile_header
