from fastapi import Depends, Request

from app.di.dependencies import get_di_container
from app.di.integrations.container import IntegrationsContainer
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient


def get_integrations_container(request: Request) -> IntegrationsContainer:
    return get_di_container(request).integrations()


def get_sdwan_api_client(
    integrations_container: IntegrationsContainer = Depends(get_integrations_container),
) -> ISDWANCspHttpClient:
    return integrations_container.sdwan_http_client()
