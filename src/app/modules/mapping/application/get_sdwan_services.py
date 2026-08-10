from dataclasses import dataclass

from app.integrations.sdwan_csp_api.gateways.models import SdwanService
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort


@dataclass(frozen=True, slots=True)
class GetSdwanServicesResult:
    services: list[SdwanService]


class GetSdwanServicesUseCase:

    def __init__(
        self,
        sdwan_gateway: MappingSDWANGatewayPort,
    ):
        self.sdwan_gateway = sdwan_gateway

    async def execute(self) -> GetSdwanServicesResult:
        services: list[SdwanService] = await self.sdwan_gateway.get_services()
        return GetSdwanServicesResult(services=services)
