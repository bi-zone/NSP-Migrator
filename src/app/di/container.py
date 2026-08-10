from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.core.config import settings
from app.di.infrastructure.container import InfrastructureContainer
from app.di.integrations.container import IntegrationsContainer
from app.modules.canonical.di.container import CanonicalModuleContainer
from app.modules.execute.di.container import ExecuteModuleContainer
from app.modules.imports.cisco_asa.di.container import CiscoAsaModuleContainer
from app.modules.imports.di.container import ImportsModuleContainer
from app.modules.mapping.di.container import MappingModuleContainer
from app.modules.trace.di.container import TraceModuleContainer


class AppContainer(DeclarativeContainer):
    # -- config
    config = providers.Configuration(pydantic_settings=[settings])
    app_settings = providers.Object(settings)

    # -- core containers
    infrastructure = providers.Container(
        InfrastructureContainer,
        config=config,
    )

    integrations = providers.Container(
        IntegrationsContainer,
        config=config,
        infrastructure_container=infrastructure,
    )

    # -- modules containers
    canonical_module = providers.Container(
        CanonicalModuleContainer,
        session_factory=infrastructure.session_factory,
    )

    mapping_module = providers.Container(
        MappingModuleContainer,
        canonical_module=canonical_module,
        session_factory=infrastructure.session_factory,
        sdwan_http_client=integrations.sdwan_http_client,
        catalog_gateway=integrations.sdwan_catalog_gateway,
    )

    execute_module = providers.Container(
        ExecuteModuleContainer,
        mapping_module=mapping_module,
        session_factory=infrastructure.session_factory,
        sdwan_http_client=integrations.sdwan_http_client,
        catalog_gateway=integrations.sdwan_catalog_gateway,
    )

    imports_module = providers.Container(
        ImportsModuleContainer,
        session_factory=infrastructure.session_factory,
    )

    trace_module = providers.Container(
        TraceModuleContainer,
        session_factory=infrastructure.session_factory,
    )

    cisco_asa_module = providers.Container(
        CiscoAsaModuleContainer,
        imports_module=imports_module,
        canonical_module=canonical_module,
        trace_module=trace_module,
    )


def create_di_container() -> AppContainer:
    return AppContainer()
