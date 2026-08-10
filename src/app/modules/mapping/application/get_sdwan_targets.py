from dataclasses import dataclass

from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort


@dataclass(frozen=True, slots=True)
class GetSdwanTargetsResult:
    targets: list[SdwanDeviceObject]


class GetSdwanTargetsUseCase:

    def __init__(
        self,
        sdwan_gateway: MappingSDWANGatewayPort,
    ):
        self.sdwan_gateway = sdwan_gateway

    async def execute(self) -> GetSdwanTargetsResult:
        targets: list[SdwanDeviceObject] = await self.sdwan_gateway.get_device_objects()
        return GetSdwanTargetsResult(
            targets=list(
                filter(lambda t: t.cpe_id is not None, targets)
            )  # only CPE device objects now
        )
