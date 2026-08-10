from dataclasses import dataclass

from app.integrations.sdwan_csp_api.gateways.models import SdwanZone
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort


@dataclass(frozen=True, slots=True)
class GetSdwanZonesResult:
    zones: list[SdwanZone]


class GetSdwanZonesUseCase:

    def __init__(
        self,
        sdwan_gateway: MappingSDWANGatewayPort,
    ):
        self.sdwan_gateway = sdwan_gateway

    async def execute(self) -> GetSdwanZonesResult:
        zones: list[SdwanZone] = await self.sdwan_gateway.get_zones()
        return GetSdwanZonesResult(zones=zones)
