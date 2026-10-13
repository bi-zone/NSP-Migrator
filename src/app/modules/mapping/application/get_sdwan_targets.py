from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort


@dataclass(frozen=True, slots=True)
class GetSdwanTargetsQuery:
    csp_profile_id: UUID
    vpc_id: str


@dataclass(frozen=True, slots=True)
class GetSdwanTargetsResult:
    targets: list[SdwanDeviceObject]


class GetSdwanTargetsUseCase:
    def __init__(
        self,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ):
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(self, query: GetSdwanTargetsQuery) -> GetSdwanTargetsResult:
        """Returns and devices (CPEs) and groups"""
        async with self.sdwan_gateway_provider.acquire(
            query.csp_profile_id,
            query.vpc_id,
        ) as sdwan_gateway:
            targets: list[SdwanDeviceObject] = await sdwan_gateway.get_device_objects()

        return GetSdwanTargetsResult(targets=targets)
