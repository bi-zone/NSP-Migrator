from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.modules.canonical.di.container import CanonicalModuleContainer
from app.modules.mapping.adapters.canonical_reader import CanonicalReader
from app.modules.mapping.adapters.db.uow import MappingUOW
from app.modules.mapping.adapters.sdwan_gateway import MappingSDWANGateway
from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeUseCase,
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
    canonical_module: CanonicalModuleContainer = providers.DependenciesContainer()

    # -- dependencies
    session_factory = providers.Dependency()
    sdwan_http_client: ISDWANCspHttpClient = providers.Dependency()
    catalog_gateway: SDWANCatalogGatewayPort = providers.Dependency()

    # -- uow
    uow = providers.Factory(
        MappingUOW,
        session_factory=session_factory,
    )

    # -- gateways
    sdwan_gateway = providers.Singleton(
        MappingSDWANGateway,
        sdwan_http_client=sdwan_http_client,
        catalog_gateway=catalog_gateway,
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
        uow=uow,
        sdwan_gateway=sdwan_gateway,
        canonical_reader=canonical_reader,
    )

    get_mapping_scope_rules_use_case = providers.Singleton(
        GetMappingScopeRulesUseCase,
        uow=uow,
    )

    get_mapping_scope_rules_projection_use_case = providers.Singleton(
        GetMappingScopeRulesProjectionUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
        canonical_reader=canonical_reader,
    )

    get_mapping_scope_use_case = providers.Singleton(
        GetMappingScopeUseCase,
        uow=uow,
    )

    get_mapping_entity_result_details_use_case = providers.Singleton(
        GetMappingEntityResultDetailsUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
    )

    assign_zone_for_scope_use_case = providers.Singleton(
        AssignZoneForScopeUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
    )

    select_entity_candidate_use_case = providers.Singleton(
        SelectEntityCandidateUseCase,
        uow=uow,
    )

    select_sdwan_entity_directly_use_case = providers.Singleton(
        SelectSdwanEntityDirectlyUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
    )

    get_sdwan_zones_use_case = providers.Singleton(
        GetSdwanZonesUseCase,
        sdwan_gateway=sdwan_gateway,
    )

    get_sdwan_services_use_case = providers.Singleton(
        GetSdwanServicesUseCase,
        sdwan_gateway=sdwan_gateway,
    )

    get_sdwan_addr_objects_use_case = providers.Singleton(
        GetSdwanAddrObjectsUseCase,
        sdwan_gateway=sdwan_gateway,
    )

    get_sdwan_targets_use_case = providers.Singleton(
        GetSdwanTargetsUseCase,
        sdwan_gateway=sdwan_gateway,
    )

    select_entity_with_create_on_sdwan_use_case = providers.Singleton(
        SelectEntityWithCreateOnSdwanUseCase,
        uow=uow,
        sdwan_gateway=sdwan_gateway,
        canonical_reader=canonical_reader,
    )

    auto_select_entities_with_create_use_case = providers.Singleton(
        AutoSelectEntitiesWithCreateForScopeUseCase,
        uow=uow,
        select_with_create=select_entity_with_create_on_sdwan_use_case,
    )

    get_mapping_scopes_use_case = providers.Singleton(
        GetMappingScopesUseCase,
        uow=uow,
    )
