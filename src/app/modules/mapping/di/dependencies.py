from fastapi import Request

from app.di.dependencies import get_di_container
from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeUseCase,
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
from app.modules.mapping.di.container import MappingModuleContainer


def get_mapping_module_container(request: Request) -> MappingModuleContainer:
    return get_di_container(request).mapping_module()


# -- use cases
def get_map_canonical_to_sdwan_use_case(request: Request) -> MapCanonicalToSdwanUseCase:
    return get_mapping_module_container(request).map_canonical_to_sdwan_use_case()


def get_mapped_rules_use_case_dep(request: Request) -> GetMappingScopeRulesUseCase:
    return get_mapping_module_container(request).get_mapping_scope_rules_use_case()


def get_mapping_scope_rules_projection_use_case_dep(
    request: Request,
) -> GetMappingScopeRulesProjectionUseCase:
    return get_mapping_module_container(
        request
    ).get_mapping_scope_rules_projection_use_case()


def get_assign_zone_for_scope_use_case(request: Request) -> AssignZoneForScopeUseCase:
    return get_mapping_module_container(request).assign_zone_for_scope_use_case()


def get_select_entity_candidate_use_case(
    request: Request,
) -> SelectEntityCandidateUseCase:
    return get_mapping_module_container(request).select_entity_candidate_use_case()


def get_select_sdwan_entity_directly_use_case(
    request: Request,
) -> SelectSdwanEntityDirectlyUseCase:
    return get_mapping_module_container(request).select_sdwan_entity_directly_use_case()


def get_sdwan_zones_use_case_dep(request: Request) -> GetSdwanZonesUseCase:
    return get_mapping_module_container(request).get_sdwan_zones_use_case()


def get_sdwan_services_use_case_dep(request: Request) -> GetSdwanServicesUseCase:
    return get_mapping_module_container(request).get_sdwan_services_use_case()


def get_sdwan_addr_objects_use_case_dep(request: Request) -> GetSdwanAddrObjectsUseCase:
    return get_mapping_module_container(request).get_sdwan_addr_objects_use_case()


def get_sdwan_targets_use_case_dep(request: Request) -> GetSdwanTargetsUseCase:
    return get_mapping_module_container(request).get_sdwan_targets_use_case()


def get_select_entity_with_create_on_sdwan_use_case(
    request: Request,
) -> SelectEntityWithCreateOnSdwanUseCase:
    return get_mapping_module_container(
        request
    ).select_entity_with_create_on_sdwan_use_case()


def get_auto_select_entities_with_create_use_case(
    request: Request,
) -> AutoSelectEntitiesWithCreateForScopeUseCase:
    return get_mapping_module_container(
        request
    ).auto_select_entities_with_create_use_case()


def get_mapping_scope_use_case_dep(request: Request) -> GetMappingScopeUseCase:
    return get_mapping_module_container(request).get_mapping_scope_use_case()


def get_mapping_scopes_use_case_dep(request: Request) -> GetMappingScopesUseCase:
    return get_mapping_module_container(request).get_mapping_scopes_use_case()
