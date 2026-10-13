from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfQuery,
    GenerateReportPdfUseCase,
)
from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.domain.value_objects import ReportEnvironmentSnapshot
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


class _ReportsRepository:
    def __init__(self, report: Report | None) -> None:
        self.report = report
        self.calls: list[UUID] = []

    async def get_report_by_id(self, report_id: UUID) -> Report | None:
        self.calls.append(report_id)
        return self.report


class _Uow:
    def __init__(self, reports: _ReportsRepository) -> None:
        self.session = None
        self.reports = reports

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    def __call__(self, reuse_session: bool = False) -> _Uow:
        return self

    async def commit(self) -> None:
        pass


class _CSPProfileHeadersReader:
    def __init__(self, header: CSPProfileHeaderDTO) -> None:
        self.header = header
        self.calls: list[UUID] = []

    async def get_header_by_id(
        self,
        profile_id: UUID,
    ) -> CSPProfileHeaderDTO:
        self.calls.append(profile_id)
        return self.header


class _PdfBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[Report, CSPProfileHeaderDTO]] = []

    def build(self, *, report: Report, csp_profile: CSPProfileHeaderDTO) -> bytes:
        self.calls.append((report, csp_profile))
        return b"%PDF-test"


def _report(*, report_id: UUID, profile_id: UUID) -> Report:
    rule = ReportRule(
        id=uuid4(),
        report_id=report_id,
        policy_name="allow-web",
        action=ReportRuleAction.ACCEPT,
        priority=10,
        src_zone_names=("LAN",),
        dst_zone_names=("WAN",),
        src_addr_values=("10.10.0.0/24",),
        dst_addr_values=("203.0.113.10",),
        service_values=("tcp/443",),
        migration_result=ReportRuleMigrationResult.PUSHED,
        reason="Success",
    )
    return Report(
        id=report_id,
        title="Branch migration — 14.09.2026-10:00:00",
        created_at=datetime(2026, 9, 14, 10, tzinfo=UTC),
        csp_profile_id=profile_id,
        commit_id=42,
        environment=ReportEnvironmentSnapshot(
            project_name="Firewall migration",
            vpc_id="vpc-1",
            target_name="Branch gateway",
            target_id="target-1",
        ),
        rules=(rule,),
    )


@pytest.mark.asyncio
async def test_generate_report_pdf_loads_complete_report_and_builds_document() -> None:
    report_id = uuid4()
    profile_id = uuid4()
    report = _report(report_id=report_id, profile_id=profile_id)
    repository = _ReportsRepository(report)
    profile_header = CSPProfileHeaderDTO(
        id=profile_id,
        name="Production",
        base_url="https://example.com",
    )
    profile_reader = _CSPProfileHeadersReader(profile_header)
    pdf_builder = _PdfBuilder()
    use_case = GenerateReportPdfUseCase(  # type: ignore[arg-type]
        _Uow(repository),
        profile_reader,
        pdf_builder,
    )

    result = await use_case.execute(GenerateReportPdfQuery(report_id=report_id))

    assert result.content == b"%PDF-test"
    assert repository.calls == [report_id]
    assert profile_reader.calls == [profile_id]
    assert pdf_builder.calls == [(report, profile_header)]


@pytest.mark.asyncio
async def test_generate_report_pdf_raises_not_found_without_building() -> None:
    report_id = uuid4()
    repository = _ReportsRepository(None)
    profile_reader = _CSPProfileHeadersReader(
        CSPProfileHeaderDTO(
            id=uuid4(),
            name="Production",
            base_url="https://example.com",
        )
    )
    pdf_builder = _PdfBuilder()
    use_case = GenerateReportPdfUseCase(  # type: ignore[arg-type]
        _Uow(repository),
        profile_reader,
        pdf_builder,
    )

    with pytest.raises(ReportsModuleNotFoundError, match=str(report_id)):
        await use_case.execute(GenerateReportPdfQuery(report_id=report_id))

    assert repository.calls == [report_id]
    assert profile_reader.calls == []
    assert pdf_builder.calls == []
