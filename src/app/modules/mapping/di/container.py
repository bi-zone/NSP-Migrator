from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.mapping.adapters.canonical_reader import CanonicalReader
from app.modules.mapping.adapters.runtime_cache import RuntimeCacheMappingRepository
from app.modules.mapping.adapters.sdwan_gateway import MappingSDWANGatewayProvider
from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeUseCase,
)
from app.modules.mapping.application.discover_allowed_vpcs import (
    DiscoverAllowedVpcsUseCase,
)
from app.modules.mapping.application.get_mapping_entity_result_details import (
    GetMappingEntityResultDetailsUseCase,
)
from app.modules.mapping.application.get_mapping_scope import GetMappingScopeUseCase
from app.modules.mapping.application.get_mapping_scope_rules import (
    GetMappingScopeRulesUseCase,
)
from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    GetMappingScopeRulesProjectionUseCase,
)
from app.modules.mapping.application.get_mapping_scopes import (
    GetMappingScopesUseCase,
)
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsUseCase,
)
from app.modules.mapping.application.get_sdwan_services import (
    GetSdwanServicesUseCase,
)
from app.modules.mapping.application.get_sdwan_targets import GetSdwanTargetsUseCase
from app.modules.mapping.application.get_sdwan_zones import GetSdwanZonesUseCase
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanUseCase,
)
from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintUseCase,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyUseCase,
)


class MappingModuleContainer(DeclarativeContainer):
    # -- modules dependencies
    canonical_module: providers.DependenciesContainer = (
        providers.DependenciesContainer()
    )

    # -- dependencies
    sdwan_client_provider: providers.Dependency = providers.Dependency()
    runtime_cache_store: providers.Dependency = providers.Dependency()

    # -- runtime cache repositories
    mapping_repo = providers.Factory(
        RuntimeCacheMappingRepository,
        cache_store=runtime_cache_store,
    )

    # -- gateways
    sdwan_gateway_provider = providers.Singleton(
        MappingSDWANGatewayProvider,
        client_provider=sdwan_client_provider,
    )
    # -- readers
    canonical_reader = providers.Singleton(
        CanonicalReader,
        get_canonical_rules_scope=canonical_module.get_canonical_rule_scope_use_case,
        get_canonical_object=canonical_module.get_canonical_object_use_case,
    )

    # -- use cases
    map_canonical_to_sdwan_use_case = providers.Singleton(
        MapCanonicalToSdwanUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
        canonical_reader=canonical_reader,
    )

    get_mapping_scope_rules_use_case = providers.Singleton(
        GetMappingScopeRulesUseCase,
        mapping_repo=mapping_repo,
    )

    get_mapping_scope_rules_projection_use_case = providers.Singleton(
        GetMappingScopeRulesProjectionUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
        canonical_reader=canonical_reader,
    )

    get_mapping_scope_use_case = providers.Singleton(
        GetMappingScopeUseCase,
        mapping_repo=mapping_repo,
    )

    get_mapping_entity_result_details_use_case = providers.Singleton(
        GetMappingEntityResultDetailsUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    assign_zone_for_scope_use_case = providers.Singleton(
        AssignZoneForScopeUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    select_entity_candidate_use_case = providers.Singleton(
        SelectEntityCandidateUseCase,
        mapping_repo=mapping_repo,
    )

    select_sdwan_entity_directly_use_case = providers.Singleton(
        SelectSdwanEntityDirectlyUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    get_sdwan_zones_use_case = providers.Singleton(
        GetSdwanZonesUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    get_sdwan_services_use_case = providers.Singleton(
        GetSdwanServicesUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    get_sdwan_addr_objects_use_case = providers.Singleton(
        GetSdwanAddrObjectsUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    get_sdwan_targets_use_case = providers.Singleton(
        GetSdwanTargetsUseCase,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    discover_allowed_vpcs_use_case = providers.Singleton(
        DiscoverAllowedVpcsUseCase,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    refresh_mapping_scope_catalog_fingerprint_use_case = providers.Singleton(
        RefreshMappingScopeCatalogFingerprintUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
    )

    select_entity_with_create_on_sdwan_use_case = providers.Singleton(
        SelectEntityWithCreateOnSdwanUseCase,
        mapping_repo=mapping_repo,
        sdwan_gateway_provider=sdwan_gateway_provider,
        canonical_reader=canonical_reader,
        refresh_mapping_scope_catalog_fingerprint=(
            refresh_mapping_scope_catalog_fingerprint_use_case
        ),
    )

    auto_select_entities_with_create_use_case = providers.Singleton(
        AutoSelectEntitiesWithCreateForScopeUseCase,
        mapping_repo=mapping_repo,
        select_with_create=select_entity_with_create_on_sdwan_use_case,
        refresh_mapping_scope_catalog_fingerprint=(
            refresh_mapping_scope_catalog_fingerprint_use_case
        ),
    )

    get_mapping_scopes_use_case = providers.Singleton(
        GetMappingScopesUseCase,
        mapping_repo=mapping_repo,
    )
