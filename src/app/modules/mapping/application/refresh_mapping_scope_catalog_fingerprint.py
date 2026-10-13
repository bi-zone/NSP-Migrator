from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.mapping.domain.entities import MappingScope
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class RefreshMappingScopeCatalogFingerprintCommand:
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class RefreshMappingScopeCatalogFingerprintResult:
    mapping_scope: MappingScope
    catalog_fingerprint_changed: bool


class RefreshMappingScopeCatalogFingerprintUseCase:
    """Refresh one mapping scope's catalog baseline after SD-WAN writes."""

    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ) -> None:
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(
        self,
        command: RefreshMappingScopeCatalogFingerprintCommand,
    ) -> RefreshMappingScopeCatalogFingerprintResult:
        mapping_scope = await self.mapping_repo.get_scope_by_id(
            command.mapping_scope_id
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {command.mapping_scope_id} not found"
            )

        async with self.sdwan_gateway_provider.acquire(
            mapping_scope.csp_profile_id,
            mapping_scope.vpc_id,
        ) as sdwan_gateway:
            catalog: SdwanFullCatalog = await sdwan_gateway.get_sdwan_full_catalog()
            catalog_fingerprint: str = catalog.get_fingerprint()

        if catalog_fingerprint == mapping_scope.catalog_fingerprint:
            return RefreshMappingScopeCatalogFingerprintResult(
                mapping_scope=mapping_scope,
                catalog_fingerprint_changed=False,
            )

        refreshed_mapping_scope = await self.mapping_repo.refresh_catalog_fingerprint(
            scope_id=mapping_scope.id,
            catalog_fingerprint=catalog_fingerprint,
        )
        return RefreshMappingScopeCatalogFingerprintResult(
            mapping_scope=refreshed_mapping_scope,
            catalog_fingerprint_changed=True,
        )
