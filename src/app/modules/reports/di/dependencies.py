from fastapi import Request

from app.di.dependencies import get_di_container
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfUseCase,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersUseCase,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesUseCase,
)
from app.modules.reports.di.container import ReportsModuleContainer


def get_reports_module_container(request: Request) -> ReportsModuleContainer:
    return get_di_container(request).reports_module()


def get_report_headers_use_case(request: Request) -> GetReportHeadersUseCase:
    return get_reports_module_container(request).get_report_headers_use_case()


def get_generate_report_pdf_use_case(request: Request) -> GenerateReportPdfUseCase:
    return get_reports_module_container(request).generate_report_pdf_use_case()


def get_report_rules_use_case(request: Request) -> GetReportRulesUseCase:
    return get_reports_module_container(request).get_report_rules_use_case()
