from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.execute.adapters.mapping_reader import MappingReader
from app.modules.execute.adapters.reports_writer import ExecuteReportsWriter
from app.modules.execute.adapters.runtime_cache import RuntimeCacheExecuteRepository
from app.modules.execute.adapters.sdwan_gateway import ExecuteSDWANGatewayProvider
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesUseCase,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesUseCase,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanUseCase,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesUseCase,
)


class ExecuteModuleContainer(DeclarativeContainer):
    # -- modules dependencies
    mapping_module: providers.DependenciesContainer = providers.DependenciesContainer()
    reports_module: providers.DependenciesContainer = providers.DependenciesContainer()

    # -- dependencies
    sdwan_client_provider: providers.Dependency = providers.Dependency()
    runtime_cache_store: providers.Dependency = providers.Dependency()

    # -- runtime cache repository
    execute_repo = providers.Factory(
        RuntimeCacheExecuteRepository,
        cache_store=runtime_cache_store,
    )

    # -- gateways
    sdwan_gateway_provider = providers.Singleton(
        ExecuteSDWANGatewayProvider,
        client_provider=sdwan_client_provider,
    )

    # -- readers
    mapping_reader = providers.Singleton(
        MappingReader,
        get_mapped_rules=mapping_module.get_mapping_scope_rules_use_case,
        get_mapping_scope=mapping_module.get_mapping_scope_use_case,
    )

    reports_writer = providers.Factory(
        ExecuteReportsWriter,
        save_report_use_case=reports_module.save_report_use_case,
    )

    # -- use cases
    prepare_execute_plan_use_case = providers.Singleton(
        PrepareExecutePlanUseCase,
        execute_repo=execute_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
        mapping_reader=mapping_reader,
    )

    push_execute_plan_rules_use_case = providers.Singleton(
        PushExecutePlanRulesUseCase,
        execute_repo=execute_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
        mapping_reader=mapping_reader,
        reports_writer=reports_writer,
    )

    get_execute_plan_rules_use_case = providers.Singleton(
        GetExecutePlanRulesUseCase,
        execute_repo=execute_repo,
    )

    get_sdwan_rules_use_case = providers.Singleton(
        GetSdwanRulesUseCase,
        sdwan_gateway_provider=sdwan_gateway_provider,
        mapping_reader=mapping_reader,
    )
