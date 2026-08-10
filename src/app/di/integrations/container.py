from dependency_injector import containers, providers

from app.core.config import ApplicationSettings
from app.di.infrastructure.container import InfrastructureContainer
from app.integrations.sdwan_csp_api.client import SDWANCspHttpClient
from app.integrations.sdwan_csp_api.gateways.catalog import SDWANCatalogGateway


class IntegrationsContainer(containers.DeclarativeContainer):
    config: ApplicationSettings = providers.Configuration()

    infrastructure_container: InfrastructureContainer = (
        providers.DependenciesContainer()
    )

    # -- SD-WAN CSP API Client
    sdwan_http_client = providers.Factory(
        SDWANCspHttpClient,
        base_url=config.integrations.sdwan_csp_api.base_url,
        username=config.integrations.sdwan_csp_api.username,
        password=config.integrations.sdwan_csp_api.password,
        vpc_id=config.integrations.sdwan_csp_api.vpc_id,
        requester=providers.Factory(
            infrastructure_container.http_requester_factory,
            verify_server_ssl=False,
            cert_path=config.integrations.sdwan_csp_api.cert_path,
            timeout=20.0,
        ),
    )

    # -- common gateways
    sdwan_catalog_gateway = providers.Singleton(
        SDWANCatalogGateway,
        sdwan_http_client=sdwan_http_client,
    )
