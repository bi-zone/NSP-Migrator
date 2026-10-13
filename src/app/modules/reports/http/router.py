"""Report-history HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.fastapi.querying import PaginationResponse
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfQuery,
    GenerateReportPdfUseCase,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersResult,
    GetReportHeadersUseCase,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesResult,
    GetReportRulesUseCase,
)
from app.modules.reports.di.dependencies import (
    get_generate_report_pdf_use_case,
    get_report_headers_use_case,
    get_report_rules_use_case,
)
from app.modules.reports.http.query_params import (
    ReportHeadersQueryParams,
    ReportRulesQueryParams,
)
from app.modules.reports.http.schemas import (
    ReportHeaderResponse,
    ReportHeadersListResponse,
    ReportRuleResponse,
    ReportRulesListResponse,
)

reports_router = APIRouter(prefix="/reports", tags=["reports"])


@reports_router.get(
    "",
    response_model=ReportHeadersListResponse,
    summary="List migration reports",
)
async def list_report_headers(
    params: Annotated[ReportHeadersQueryParams, Query()],
    use_case: Annotated[
        GetReportHeadersUseCase,
        Depends(get_report_headers_use_case),
    ],
) -> ReportHeadersListResponse:
    """Get reports list with filters using"""
    result: GetReportHeadersResult = await use_case.execute(
        query=params.to_application_query()
    )
    return ReportHeadersListResponse(
        reports=[
            ReportHeaderResponse.model_validate(report) for report in result.reports
        ],
        pagination=PaginationResponse.model_validate(
            result.pagination,
            from_attributes=True,
        ),
    )


@reports_router.get(
    "/{report_id}/pdf",
    response_class=Response,
    summary="Download a migration report as PDF",
)
async def download_report_pdf(
    report_id: UUID,
    use_case: Annotated[
        GenerateReportPdfUseCase,
        Depends(get_generate_report_pdf_use_case),
    ],
) -> Response:
    """Generate and download the complete immutable report snapshot."""
    result = await use_case.execute(GenerateReportPdfQuery(report_id=report_id))
    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="migration-report-{report_id}.pdf"'
            )
        },
    )


@reports_router.get(
    "/{report_id}/rules",
    response_model=ReportRulesListResponse,
    summary="List saved policy outcomes for a migration report",
)
async def list_report_rules(
    report_id: UUID,
    params: Annotated[ReportRulesQueryParams, Query()],
    use_case: Annotated[
        GetReportRulesUseCase,
        Depends(get_report_rules_use_case),
    ],
) -> ReportRulesListResponse:
    """Get one report's saved policy outcomes with filters and pagination."""
    result: GetReportRulesResult = await use_case.execute(
        query=params.to_application_query(report_id)
    )
    return ReportRulesListResponse(
        rules=[ReportRuleResponse.model_validate(rule) for rule in result.rules],
        pagination=PaginationResponse.model_validate(
            result.pagination,
        ),
    )
