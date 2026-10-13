from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

import streamlit as st

from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
)
from app.modules.mapping.application.dto import MappingEntityResultDetailsDTO
from app.modules.mapping.application.get_mapping_entity_result_details import (
    GetMappingEntityResultDetailsQuery,
)
from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    GetMappingScopeRulesProjectionQuery,
    GetMappingScopeRulesProjectionResult,
)
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsQuery,
    GetSdwanAddrObjectsResult,
)
from app.modules.mapping.application.get_sdwan_services import (
    GetSdwanServicesQuery,
    GetSdwanServicesResult,
)
from app.modules.mapping.application.get_sdwan_zones import (
    GetSdwanZonesQuery,
)
from app.modules.mapping.domain.enums import MappingEntityType
from app.modules.trace.application.dto import (
    GetTraceForEntityQuery,
    TraceRecordDTO,
)
from app.modules.trace.domain.enums import TraceCanonicalKind
from streamlit_app.components.mapped_rules.canonical_evidence import (
    CanonicalObjectEvidence,
)
from streamlit_app.components.mapped_rules.utils import (
    MappedRulesProjectionState,
)
from streamlit_app.services.sdwan import SdwanEntity, sdwan_item_str_value
from streamlit_app.services.use_cases import (
    get_canonical_object,
    get_mapping_entity_result_details,
    get_mapping_scope_rules_projection,
    get_sdwan_addr_objects,
    get_sdwan_services,
    get_sdwan_zones,
    get_trace_for_entity,
    run_async,
)
from streamlit_app.session.context import get_context

T = TypeVar("T")

_PROJECTION_CACHE_KEY = "mapped_rules_projection_cache"
_MAPPING_RESULT_DETAILS_CACHE_KEY = "mapped_rules_mapping_result_details_cache"
_SDWAN_CATALOG_ROWS_CACHE_KEY = "mapped_rules_sdwan_catalog_rows_cache"
_CANONICAL_OBJECT_EVIDENCE_CACHE_KEY = "mapped_rules_canonical_object_evidence_cache"


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
    mapping_scope_id: UUID,
    mapping_result_id: UUID,
) -> MappingEntityResultDetailsDTO:
    """
    Load selected mapping result details once.

    This prevents candidate/direct-selection reruns from reloading candidates and
    SD-WAN display data over and over again.
    """
    return _get_or_load(
        cache_name=_MAPPING_RESULT_DETAILS_CACHE_KEY,
        item_key=_mapping_result_details_cache_key(
            mapping_scope_id=mapping_scope_id,
            mapping_result_id=mapping_result_id,
        ),
        load_func=lambda: _load_mapping_result_details_uncached(
            mapping_scope_id=mapping_scope_id,
            mapping_result_id=mapping_result_id,
        ),
    )


def load_cached_canonical_object_evidence(
    canonical_snapshot_id: UUID,
    canonical_entity_id: UUID,
) -> CanonicalObjectEvidence:
    """Load immutable canonical fields and source trace once per object."""
    return _get_or_load(
        cache_name=_CANONICAL_OBJECT_EVIDENCE_CACHE_KEY,
        item_key=_canonical_object_evidence_cache_key(
            canonical_snapshot_id=canonical_snapshot_id,
            canonical_entity_id=canonical_entity_id,
        ),
        load_func=lambda: _load_canonical_object_evidence_uncached(
            canonical_snapshot_id=canonical_snapshot_id,
            canonical_entity_id=canonical_entity_id,
        ),
    )


def load_cached_sdwan_catalog_rows(
    mapping_scope_id: UUID,
    entity_type: MappingEntityType,
) -> list[SdwanCatalogTableRow]:
    """Cache SD-WAN catalog rows in Streamlit session state.
    Cache Key contains mapping scope to isolate caches
    of different CSP Profiles (different objects catalogs)
    """
    return _get_or_load(
        cache_name=_SDWAN_CATALOG_ROWS_CACHE_KEY,
        item_key=f"{mapping_scope_id}_{entity_type}",
        load_func=lambda: _load_sdwan_catalog_rows_uncached(entity_type),
    )


def invalidate_projection_cache(mapping_scope_id: UUID | None = None) -> None:
    _invalidate_cache_item(_PROJECTION_CACHE_KEY, mapping_scope_id)


def invalidate_mapping_result_details_cache(
    mapping_scope_id: UUID | None = None,
    mapping_result_id: UUID | None = None,
) -> None:
    if mapping_scope_id is None or mapping_result_id is None:
        _invalidate_cache_item(_MAPPING_RESULT_DETAILS_CACHE_KEY, None)
        return
    _invalidate_cache_item(
        _MAPPING_RESULT_DETAILS_CACHE_KEY,
        _mapping_result_details_cache_key(
            mapping_scope_id=mapping_scope_id,
            mapping_result_id=mapping_result_id,
        ),
    )


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
    invalidate_mapping_result_details_cache(
        mapping_scope_id=mapping_scope_id,
        mapping_result_id=mapping_result_id,
    )


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


def _mapping_result_details_cache_key(
    *,
    mapping_scope_id: UUID,
    mapping_result_id: UUID,
) -> str:
    return f"{mapping_scope_id}:{mapping_result_id}"


def _canonical_object_evidence_cache_key(
    *,
    canonical_snapshot_id: UUID,
    canonical_entity_id: UUID,
) -> str:
    return f"{canonical_snapshot_id}:{canonical_entity_id}"


def _load_mapping_result_details_uncached(
    mapping_scope_id: UUID,
    mapping_result_id: UUID,
) -> MappingEntityResultDetailsDTO:
    result = run_async(
        get_mapping_entity_result_details().execute(
            GetMappingEntityResultDetailsQuery(
                mapping_scope_id=mapping_scope_id,
                mapping_result_id=mapping_result_id,
            )
        )
    )
    return result.details


def _load_canonical_object_evidence_uncached(
    *,
    canonical_snapshot_id: UUID,
    canonical_entity_id: UUID,
) -> CanonicalObjectEvidence:
    canonical_result = run_async(
        get_canonical_object().execute(
            GetCanonicalObjectQuery(
                canonical_snapshot_id=canonical_snapshot_id,
                object_id=canonical_entity_id,
                include_members=False,
            )
        )
    )
    trace_records: list[TraceRecordDTO] = run_async(
        get_trace_for_entity().execute(
            GetTraceForEntityQuery(
                canonical_kind=TraceCanonicalKind.OBJECT,
                canonical_id=canonical_entity_id,
            )
        )
    )
    return CanonicalObjectEvidence(
        canonical_object=canonical_result.object,
        trace_records=[
            record
            for record in trace_records
            if record.canonical_snapshot_id == canonical_snapshot_id
        ],
    )


def _load_sdwan_catalog_rows_uncached(
    entity_type: MappingEntityType,
) -> list[SdwanCatalogTableRow]:
    mapping_scope_id = get_context().mapping_scope_id
    if mapping_scope_id is None:
        raise ValueError("Mapping scope is required")

    def _sdwan_catalog_row(
        item: SdwanEntity,
    ) -> SdwanCatalogTableRow:
        return SdwanCatalogTableRow(
            id=str(item.id),
            name=item.name,
            value=sdwan_item_str_value(item),
        )

    if entity_type == MappingEntityType.ZONE:
        zones_result = run_async(
            get_sdwan_zones().execute(GetSdwanZonesQuery(mapping_scope_id))
        )
        return [_sdwan_catalog_row(item) for item in zones_result.zones]

    if entity_type == MappingEntityType.ADDR:
        addr_objs_result: GetSdwanAddrObjectsResult = run_async(
            get_sdwan_addr_objects().execute(GetSdwanAddrObjectsQuery(mapping_scope_id))
        )
        return [_sdwan_catalog_row(item) for item in addr_objs_result.addr_objects]

    if entity_type == MappingEntityType.SERVICE:
        services_result: GetSdwanServicesResult = run_async(
            get_sdwan_services().execute(GetSdwanServicesQuery(mapping_scope_id))
        )
        return [_sdwan_catalog_row(item) for item in services_result.services]

    raise ValueError(f"Unexpected entity type {entity_type}")
