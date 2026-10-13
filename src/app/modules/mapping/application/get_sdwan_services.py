from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanService
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class GetSdwanServicesQuery:
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class GetSdwanServicesResult:
    services: list[SdwanService]


class GetSdwanServicesUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ):
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(self, query: GetSdwanServicesQuery) -> GetSdwanServicesResult:
        scope = await self.mapping_repo.get_scope_by_id(query.mapping_scope_id)
        if scope is None:
            raise MappingModuleNotFoundError("Mapping scope not found")
        async with self.sdwan_gateway_provider.acquire(
            scope.csp_profile_id,
            scope.vpc_id,
        ) as sdwan_gateway:
            services: list[SdwanService] = await sdwan_gateway.get_services()
        return GetSdwanServicesResult(services=services)
