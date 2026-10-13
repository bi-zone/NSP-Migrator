from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.reports.adapters.csp_profile_headers_reader import (
    SettingsCSPProfileHeadersReader,
)
from app.modules.reports.adapters.db.uow import ReportsUnitOfWork
from app.modules.reports.adapters.sdwan_gateway import ReportsSDWANGatewayProvider
from app.modules.reports.application.services.report_pdf_builder import ReportPdfBuilder
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfUseCase,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersUseCase,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesUseCase,
)
from app.modules.reports.application.use_cases.save_report import SaveReportUseCase


class ReportsModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()
    sdwan_client_provider: providers.Dependency = providers.Dependency()
    list_profiles_use_case: providers.Dependency = providers.Dependency()
    get_profile_use_case: providers.Dependency = providers.Dependency()

    uow = providers.Factory(ReportsUnitOfWork, session_factory=session_factory)

    sdwan_gateway_provider = providers.Singleton(
        ReportsSDWANGatewayProvider,
        client_provider=sdwan_client_provider,
    )

    csp_profile_headers_reader = providers.Factory(
        SettingsCSPProfileHeadersReader,
        list_profiles_use_case=list_profiles_use_case,
        get_profile_use_case=get_profile_use_case,
    )

    save_report_use_case = providers.Factory(
        SaveReportUseCase,
        uow=uow,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    get_report_headers_use_case = providers.Factory(
        GetReportHeadersUseCase,
        uow=uow,
        csp_profile_headers_reader=csp_profile_headers_reader,
    )

    get_report_rules_use_case = providers.Factory(
        GetReportRulesUseCase,
        uow=uow,
    )

    report_pdf_builder = providers.Factory(ReportPdfBuilder)

    generate_report_pdf_use_case = providers.Factory(
        GenerateReportPdfUseCase,
        uow=uow,
        csp_profile_headers_reader=csp_profile_headers_reader,
        pdf_builder=report_pdf_builder,
    )
