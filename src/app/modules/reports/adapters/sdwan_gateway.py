from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.integrations.sdwan_csp_api.client_provider import SDWANClientProvider
from app.integrations.sdwan_csp_api.gateways.catalog import SDWANCatalogGateway
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.reports.ports.sdwan_gateway import (
    ReportsSDWANGatewayPort,
    ReportsSDWANGatewayProviderPort,
)


class ReportsSDWANGateway(ReportsSDWANGatewayPort):
    """Reports adapter over the shared SD-WAN catalog gateway."""

    def __init__(self, catalog_gateway: SDWANCatalogGatewayPort) -> None:
        self._catalog_gateway = catalog_gateway

    async def get_target(self, target_id: str) -> SdwanDeviceObject | None:
        return await self._catalog_gateway.get_sdwan_device_object(target_id)

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return await self._catalog_gateway.get_sdwan_full_catalog()


class ReportsSDWANGatewayProvider(ReportsSDWANGatewayProviderPort):
    """Create isolated Reports gateways through the shared client lifecycle."""

    def __init__(self, client_provider: SDWANClientProvider) -> None:
        self._client_provider = client_provider

    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]:
        return await self._client_provider.discover_vpcs(profile_id)

    @asynccontextmanager
    async def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AsyncIterator[ReportsSDWANGateway]:
        async with self._client_provider.acquire(profile_id, vpc_id) as client:
            yield ReportsSDWANGateway(SDWANCatalogGateway(client))
