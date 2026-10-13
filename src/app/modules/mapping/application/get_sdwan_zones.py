from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanZone
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class GetSdwanZonesQuery:
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class GetSdwanZonesResult:
    zones: list[SdwanZone]


class GetSdwanZonesUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ):
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(self, query: GetSdwanZonesQuery) -> GetSdwanZonesResult:
        scope = await self.mapping_repo.get_scope_by_id(query.mapping_scope_id)
        if scope is None:
            raise MappingModuleNotFoundError("Mapping scope not found")
        async with self.sdwan_gateway_provider.acquire(
            scope.csp_profile_id,
            scope.vpc_id,
        ) as sdwan_gateway:
            zones: list[SdwanZone] = await sdwan_gateway.get_zones()
        return GetSdwanZonesResult(zones=zones)
