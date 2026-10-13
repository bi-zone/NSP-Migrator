from uuid import uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import SdwanServiceL4Proto
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanFullCatalog,
    SdwanService,
)
from app.modules.mapping.domain.enums import MappingResultStatus
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalScopeEntities,
    CanonicalService,
    CanonicalServiceKind,
)
from app.modules.mapping.services.mapping_objects.mapping_objects_service import (
    MappingObjectsService,
)
from app.modules.mapping.services.mapping_objects.matchers.services_matcher import (
    ServiceMatcher,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.services_catalog_index import (
    SdwanServicesCatalogIndex,
)


def test_explicit_any_service_matches_sdwan_any() -> None:
    any_service = SdwanService(
        id=1,
        name="ANY",
        l4_proto=SdwanServiceL4Proto.ANY,
        ranges=None,
        codes=None,
    )
    matcher = ServiceMatcher(SdwanServicesCatalogIndex([any_service]))

    candidates = matcher.match(
        CanonicalService(
            id=uuid4(),
            kind=CanonicalServiceKind.ANY_SERVICE,
            name="any",
        )
    )

    assert [candidate.sdwan_entity_id for candidate in candidates] == [1]


@pytest.mark.parametrize("protocol", ["ip", "4", "esp", "ah", "gre", "tcp-udp"])
def test_ip_proto_does_not_match_same_named_sdwan_service(protocol: str) -> None:
    sdwan_service = SdwanService(
        id=1,
        name=protocol,
        l4_proto=SdwanServiceL4Proto.IP_IP,
        ranges=None,
        codes=None,
    )
    matcher = ServiceMatcher(SdwanServicesCatalogIndex([sdwan_service]))

    candidates = matcher.match(
        CanonicalService(
            id=uuid4(),
            kind=CanonicalServiceKind.IP_PROTO,
            name=protocol,
            protocol=protocol,
        )
    )

    assert candidates == []


@pytest.mark.parametrize(
    ("kind", "l4_proto"),
    [
        (CanonicalServiceKind.TCP, SdwanServiceL4Proto.TCP),
        (CanonicalServiceKind.UDP, SdwanServiceL4Proto.UDP),
    ],
)
def test_l4_service_matches_only_exact_signature(
    kind: CanonicalServiceKind,
    l4_proto: SdwanServiceL4Proto,
) -> None:
    exact_signature = SdwanService(
        id=1,
        name="different-name",
        l4_proto=l4_proto,
        ranges=((443, 443),),
        codes=None,
    )
    same_name_different_signature = SdwanService(
        id=2,
        name="shared-name",
        l4_proto=l4_proto,
        ranges=((80, 80),),
        codes=None,
    )
    matcher = ServiceMatcher(
        SdwanServicesCatalogIndex(
            [exact_signature, same_name_different_signature],
        )
    )

    candidates = matcher.match(
        CanonicalService(
            id=uuid4(),
            kind=kind,
            name="shared-name",
            protocol=l4_proto.value,
            port_from=443,
            port_to=443,
        )
    )

    assert [candidate.sdwan_entity_id for candidate in candidates] == [1]


def test_icmp_service_matches_only_exact_code_set() -> None:
    exact_signature = SdwanService(
        id=1,
        name="different-name",
        l4_proto=SdwanServiceL4Proto.ICMP,
        ranges=None,
        codes=("echo_request",),
    )
    same_name_different_signature = SdwanService(
        id=2,
        name="shared-name",
        l4_proto=SdwanServiceL4Proto.ICMP,
        ranges=None,
        codes=("echo_reply",),
    )
    matcher = ServiceMatcher(
        SdwanServicesCatalogIndex(
            [exact_signature, same_name_different_signature],
        )
    )

    candidates = matcher.match(
        CanonicalService(
            id=uuid4(),
            kind=CanonicalServiceKind.ICMP,
            name="shared-name",
            protocol="icmp",
            icmp_type=8,
            icmp_code=0,
        )
    )

    assert [candidate.sdwan_entity_id for candidate in candidates] == [1]


def test_ip_proto_produces_unresolved_mapping_result() -> None:
    ip_proto = CanonicalService(
        id=uuid4(),
        kind=CanonicalServiceKind.IP_PROTO,
        name="esp",
        protocol="esp",
    )
    same_named_service = SdwanService(
        id=1,
        name="esp",
        l4_proto=SdwanServiceL4Proto.IP_IP,
        ranges=None,
        codes=None,
    )

    results = MappingObjectsService.build_results(
        mapping_scope_id=uuid4(),
        canonical_scope_entities=CanonicalScopeEntities(
            zones=[],
            addr_objects=[],
            services=[ip_proto],
        ),
        sdwan_full_catalog=SdwanFullCatalog(
            zones=[],
            addr_objs=[],
            services=[same_named_service],
            networks=[],
        ),
    )

    assert len(results) == 1
    assert results[0].canonical_entity_id == ip_proto.id
    assert results[0].result_status == MappingResultStatus.UNRESOLVED
    assert results[0].selected_sdwan_entity_id is None
