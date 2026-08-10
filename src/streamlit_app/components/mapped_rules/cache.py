from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

import streamlit as st

from app.modules.mapping.application.dto import MappingEntityResultDetailsDTO
from app.modules.mapping.application.get_mapping_entity_result_details import (
    GetMappingEntityResultDetailsQuery,
)
from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    GetMappingScopeRulesProjectionQuery,
    GetMappingScopeRulesProjectionResult,
)
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsResult,
)
from app.modules.mapping.application.get_sdwan_services import (
    GetSdwanServicesResult,
)
from app.modules.mapping.application.get_sdwan_zones import GetSdwanZonesResult
from app.modules.mapping.domain.enums import MappingEntityType
from streamlit_app.components.mapped_rules.utils import (
    MappedRulesProjectionState,
)
from streamlit_app.services.sdwan import SdwanEntity, sdwan_item_str_value
from streamlit_app.services.use_cases import (
    get_mapping_entity_result_details,
    get_mapping_scope_rules_projection,
    get_sdwan_addr_objects,
    get_sdwan_services,
    get_sdwan_zones,
    run_async,
)

T = TypeVar("T")

_PROJECTION_CACHE_KEY = "mapped_rules_projection_cache"
_MAPPING_RESULT_DETAILS_CACHE_KEY = "mapped_rules_mapping_result_details_cache"
_SDWAN_CATALOG_ROWS_CACHE_KEY = "mapped_rules_sdwan_catalog_rows_cache"


@dataclass(frozen=True, slots=True)
class SdwanCatalogTableRow:
    id: str
    name: str
    value: str


def load_cached_projection_state(mapping_scope_id: UUID) -> MappedRulesProjectionState:
    """Load heavy page projection once per scope until mapping data changes."""
    return _get_or_load(
        cache_name=_PROJECTION_CACHE_KEY,
        item_key=mapping_scope_id,
        load_func=lambda: _load_projection_state_uncached(mapping_scope_id),
    )


def load_cached_mapping_result_details(
    mapping_result_id: UUID,
) -> MappingEntityResultDetailsDTO:
    """
    Load selected mapping result details once.

    This prevents candidate/direct-selection reruns from reloading candidates and
    SD-WAN display data over and over again.
    """
    return _get_or_load(
        cache_name=_MAPPING_RESULT_DETAILS_CACHE_KEY,
        item_key=mapping_result_id,
        load_func=lambda: _load_mapping_result_details_uncached(mapping_result_id),
    )


def load_cached_sdwan_catalog_rows(
    entity_type: MappingEntityType,
) -> list[SdwanCatalogTableRow]:
    """Cache SD-WAN catalog rows in Streamlit session state."""
    return _get_or_load(
        cache_name=_SDWAN_CATALOG_ROWS_CACHE_KEY,
        item_key=entity_type,
        load_func=lambda: _load_sdwan_catalog_rows_uncached(entity_type),
    )


def invalidate_projection_cache(mapping_scope_id: UUID | None = None) -> None:
    _invalidate_cache_item(_PROJECTION_CACHE_KEY, mapping_scope_id)


def invalidate_mapping_result_details_cache(
    mapping_result_id: UUID | None = None,
) -> None:
    _invalidate_cache_item(_MAPPING_RESULT_DETAILS_CACHE_KEY, mapping_result_id)


def invalidate_sdwan_catalog_rows_cache(
    entity_type: MappingEntityType | None = None,
) -> None:
    _invalidate_cache_item(_SDWAN_CATALOG_ROWS_CACHE_KEY, entity_type)


def invalidate_after_mapping_result_mutation(
    mapping_scope_id: UUID,
    mapping_result_id: UUID | None = None,
) -> None:
    """
    Candidate/direct assignment changes mapping data, but not the SD-WAN catalog.
    """
    invalidate_projection_cache(mapping_scope_id)
    invalidate_mapping_result_details_cache(mapping_result_id)


def invalidate_after_scope_mapping_mutation(mapping_scope_id: UUID) -> None:
    """
    Bulk zone assignment changes many mapping rows. Drop projection and all opened
    mapping-result details, but keep SD-WAN catalog rows.
    """
    invalidate_projection_cache(mapping_scope_id)
    invalidate_mapping_result_details_cache()


def invalidate_after_sdwan_catalog_mutation(mapping_scope_id: UUID) -> None:
    """
    Auto-create may create SD-WAN address/service entities, so catalog cache must
    be refreshed too.
    """
    invalidate_projection_cache(mapping_scope_id)
    invalidate_mapping_result_details_cache()
    invalidate_sdwan_catalog_rows_cache()


def _get_or_load(  # noqa
    cache_name: str, item_key: str | UUID, load_func: Callable[[], T]
) -> T:
    """Get value by item_key from cache group.

    If item_key not exists in cache group (or cache group not exists) - load value by load_func and save to cache.
    """
    cache: dict[str | UUID, T] = st.session_state.setdefault(cache_name, {})
    if item_key not in cache:
        cache[item_key] = load_func()
    return cache[item_key]


def _invalidate_cache_item(cache_name: str, item_key: str | UUID | None) -> None:
    # if not provided item_key - reset cache fully by cache group name
    if item_key is None:
        st.session_state.pop(cache_name, None)
        return
    # if cache group exists - reset only for item_key
    cache: dict[str | UUID, object] | None = st.session_state.get(cache_name)
    if cache is not None:
        cache.pop(item_key, None)


def _load_projection_state_uncached(
    mapping_scope_id: UUID,
) -> MappedRulesProjectionState:
    result: GetMappingScopeRulesProjectionResult = run_async(
        get_mapping_scope_rules_projection().execute(
            GetMappingScopeRulesProjectionQuery(mapping_scope_id=mapping_scope_id)
        )
    )
    projection = result.projection

    return MappedRulesProjectionState(
        projection=projection,
        canonical_rule_by_id={
            str(rule.canonical_rule_id): rule for rule in projection.canonical_rules
        },
        mapped_rule_by_id={
            str(rule.mapping_scope_rule_id): rule for rule in projection.mapped_rules
        },
        details_by_rule_id={
            str(rule_id): details
            for rule_id, details in projection.details_by_rule_id.items()
        },
    )


def _load_mapping_result_details_uncached(
    mapping_result_id: UUID,
) -> MappingEntityResultDetailsDTO:
    result = run_async(
        get_mapping_entity_result_details().execute(
            GetMappingEntityResultDetailsQuery(mapping_result_id=mapping_result_id)
        )
    )
    return result.details


def _load_sdwan_catalog_rows_uncached(
    entity_type: MappingEntityType,
) -> list[SdwanCatalogTableRow]:

    def _sdwan_catalog_row(
        item: SdwanEntity,
    ) -> SdwanCatalogTableRow:
        return SdwanCatalogTableRow(
            id=str(item.id),
            name=item.name,
            value=sdwan_item_str_value(item),
        )

    if entity_type == MappingEntityType.ZONE:
        zones_result: GetSdwanZonesResult = run_async(get_sdwan_zones().execute())
        return [_sdwan_catalog_row(item) for item in zones_result.zones]

    if entity_type == MappingEntityType.ADDR:
        addr_objs_result: GetSdwanAddrObjectsResult = run_async(
            get_sdwan_addr_objects().execute()
        )
        return [_sdwan_catalog_row(item) for item in addr_objs_result.addr_objects]

    if entity_type == MappingEntityType.SERVICE:
        services_result: GetSdwanServicesResult = run_async(
            get_sdwan_services().execute()
        )
        return [_sdwan_catalog_row(item) for item in services_result.services]

    raise ValueError(f"Unexpected entity type {entity_type}")
