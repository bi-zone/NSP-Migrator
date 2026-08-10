from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.modules.execute.adapters.db.uow import ExecuteUOW
from app.modules.execute.adapters.mapping_reader import MappingReader
from app.modules.execute.adapters.sdwan_gateway import ExecuteSDWANGateway
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
from app.modules.mapping.di.container import MappingModuleContainer


class ExecuteModuleContainer(DeclarativeContainer):
    # -- modules dependencies
    mapping_module: MappingModuleContainer = providers.DependenciesContainer()

    # -- dependencies
    session_factory = providers.Dependency()
    sdwan_http_client: ISDWANCspHttpClient = providers.Dependency()
    catalog_gateway: SDWANCatalogGatewayPort = providers.Dependency()

    # -- uow
    uow = providers.Factory(
        ExecuteUOW,
        session_factory=session_factory,
    )

    # -- gateways
    sdwan_gateway = providers.Singleton(
        ExecuteSDWANGateway,
        sdwan_http_client=sdwan_http_client,
        catalog_gateway=catalog_gateway,
    )

    # -- readers
    mapping_reader = providers.Singleton(
        MappingReader,
        get_mapped_rules=mapping_module.get_mapping_scope_rules_use_case,
        get_mapping_scope=mapping_module.get_mapping_scope_use_case,
    )

    # -- use cases
    prepare_execute_plan_use_case = providers.Singleton(
        PrepareExecutePlanUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
        mapping_reader=mapping_reader,
    )

    push_execute_plan_rules_use_case = providers.Singleton(
        PushExecutePlanRulesUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
        mapping_reader=mapping_reader,
    )

    get_execute_plan_rules_use_case = providers.Singleton(
        GetExecutePlanRulesUseCase,
        uow=uow,
    )

    get_sdwan_rules_use_case = providers.Singleton(
        GetSdwanRulesUseCase,
        sdwan_gateway=sdwan_gateway,
    )
