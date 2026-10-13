from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort


@dataclass(frozen=True, slots=True)
class DiscoverAllowedVpcsQuery:
    csp_profile_id: UUID


@dataclass(frozen=True, slots=True)
class DiscoverAllowedVpcsResult:
    vpcs: list[AllowedVPCResponse]


class DiscoverAllowedVpcsUseCase:
    def __init__(
        self,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ) -> None:
        self._sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(
        self,
        query: DiscoverAllowedVpcsQuery,
    ) -> DiscoverAllowedVpcsResult:
        return DiscoverAllowedVpcsResult(
            vpcs=await self._sdwan_gateway_provider.discover_vpcs(
                query.csp_profile_id
            )
        )
