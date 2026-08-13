from ipaddress import IPv4Address, IPv4Network
from uuid import uuid4

from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanFullCatalog,
)
from app.modules.mapping.domain.enums import MappingResultStatus
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalScopeEntities,
)
from app.modules.mapping.services.mapping_objects.mapping_objects_service import (
    MappingObjectsService,
)
from app.modules.mapping.services.mapping_objects.matchers.addr_objs_matcher import (
    AddrObjectMatcher,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.addr_objs_catalog_index import (
    SdwanAddrObjsCatalogIndex,
)


def _matcher_with_any() -> AddrObjectMatcher:
    any_addr = SdwanAddrObject(
        id=1,
        parents=(),
        name="ANY",
        type=SdwanAddrObjectType.PREFIX,
        prefix=IPv4Network("0.0.0.0/0"),
    )
    return AddrObjectMatcher(SdwanAddrObjsCatalogIndex([any_addr]))


def test_explicit_any_address_matches_sdwan_any() -> None:
    candidates = _matcher_with_any().match(
        CanonicalAddrObject(
            id=uuid4(),
            kind=CanonicalAddrObjKind.ANY_ADDR,
            name="any",
        )
    )

    assert [candidate.sdwan_entity_id for candidate in candidates] == [1]


def test_unresolved_address_does_not_match_sdwan_any() -> None:
    candidates = _matcher_with_any().match(
        CanonicalAddrObject(
            id=uuid4(),
            kind=CanonicalAddrObjKind.UNRESOLVED_ADDR,
            name="OBJ_MISSING",
        )
    )

    assert candidates == []


def test_unresolved_address_produces_unresolved_mapping_result() -> None:
    unresolved = CanonicalAddrObject(
        id=uuid4(),
        kind=CanonicalAddrObjKind.UNRESOLVED_ADDR,
        name="OBJ_MISSING",
    )

    results = MappingObjectsService.build_results(
        mapping_scope_id=uuid4(),
        canonical_scope_entities=CanonicalScopeEntities(
            zones=[],
            addr_objects=[unresolved],
            services=[],
        ),
        sdwan_full_catalog=SdwanFullCatalog(
            zones=[],
            addr_objs=[],
            services=[],
            networks=[],
        ),
    )

    assert len(results) == 1
    assert results[0].canonical_entity_id == unresolved.id
    assert results[0].result_status == MappingResultStatus.UNRESOLVED
    assert results[0].selected_sdwan_entity_id is None


def test_same_name_does_not_match_address_with_different_value() -> None:
    sdwan_addr = SdwanAddrObject(
        id=2,
        parents=(),
        name="shared-name",
        type=SdwanAddrObjectType.HOST,
        host=IPv4Address("192.0.2.20"),
    )
    matcher = AddrObjectMatcher(SdwanAddrObjsCatalogIndex([sdwan_addr]))

    candidates = matcher.match(
        CanonicalAddrObject(
            id=uuid4(),
            kind=CanonicalAddrObjKind.HOST,
            name="shared-name",
            cidr="192.0.2.10/32",
        )
    )

    assert candidates == []
