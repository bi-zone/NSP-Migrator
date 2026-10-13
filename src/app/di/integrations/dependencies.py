from fastapi import Depends, Request

from app.di.dependencies import get_di_container
from app.di.integrations.container import IntegrationsContainer
from app.integrations.sdwan_csp_api.client_provider import SDWANClientProvider


def get_integrations_container(request: Request) -> IntegrationsContainer:
    return get_di_container(request).integrations()


def get_sdwan_client_provider(
    integrations_container: IntegrationsContainer = Depends(get_integrations_container),
) -> SDWANClientProvider:
    return integrations_container.sdwan_client_provider()
