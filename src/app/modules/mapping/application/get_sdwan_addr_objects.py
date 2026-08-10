from dataclasses import dataclass

from app.integrations.sdwan_csp_api.gateways.models import SdwanAddrObject, SdwanNetwork
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort


@dataclass(frozen=True, slots=True)
class GetSdwanAddrObjectsResult:
    addr_objects: list[SdwanAddrObject]
    networks: list[SdwanNetwork]


class GetSdwanAddrObjectsUseCase:

    def __init__(
        self,
        sdwan_gateway: MappingSDWANGatewayPort,
    ):
        self.sdwan_gateway = sdwan_gateway

    async def execute(self) -> GetSdwanAddrObjectsResult:
        addr_objects: list[SdwanAddrObject] = (
            await self.sdwan_gateway.get_addr_objects()
        )
        networks: list[SdwanNetwork] = await self.sdwan_gateway.get_networks()
        return GetSdwanAddrObjectsResult(
            addr_objects=addr_objects,
            networks=networks,
        )
