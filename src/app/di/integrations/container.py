from dependency_injector import containers, providers

from app.integrations.sdwan_csp_api.client_factory import SDWANClientFactory
from app.integrations.sdwan_csp_api.client_provider import SDWANClientProvider


class IntegrationsContainer(containers.DeclarativeContainer):
    profiles_uow: providers.Dependency = providers.Dependency()
    client_factory = providers.Singleton(SDWANClientFactory)
    sdwan_client_provider = providers.Singleton(
        SDWANClientProvider,
        uow_factory=profiles_uow.provider,
        client_factory=client_factory,
    )
