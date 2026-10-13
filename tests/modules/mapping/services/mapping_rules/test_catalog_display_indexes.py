from ipaddress import IPv4Address, IPv4Network
from uuid import uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanFullCatalog,
    SdwanService,
    SdwanZone,
)
from app.modules.mapping.domain.enums import MappingEntityType
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import CanonicalZone
from app.modules.mapping.services.mapping_rules.canonical_zones_index import (
    CanonicalZoneIndex,
)
from app.modules.mapping.services.mapping_rules.sdwan_full_catalog_index import (
    SdwanFullCatalogIndex,
)


def _catalog(
    *,
    address_objects: list[SdwanAddrObject] | None = None,
    services: list[SdwanService] | None = None,
) -> SdwanFullCatalog:
    return SdwanFullCatalog(
        zones=[SdwanZone(id=1, zone_id=10, name="LAN", type=SdwanZoneType.LAN)],
        services=services or [],
        addr_objs=address_objects or [],
        networks=[],
    )


@pytest.mark.parametrize(
    ("address_object", "expected_value"),
    [
        (
            SdwanAddrObject(
                id=10,
                parents=(),
                name="subnet",
                type=SdwanAddrObjectType.PREFIX,
                prefix=IPv4Network("192.0.2.0/24"),
            ),
            "192.0.2.0/24",
        ),
        (
            SdwanAddrObject(
                id=11,
                parents=(),
                name="host",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("192.0.2.10"),
            ),
            "192.0.2.10",
        ),
        (
            SdwanAddrObject(
                id=12,
                parents=(),
                name="fqdn",
                type=SdwanAddrObjectType.FQDN,
                fqdn="example.test",
            ),
            "example.test",
        ),
        (
            SdwanAddrObject(
                id=13,
                parents=(),
                name="range",
                type=SdwanAddrObjectType.IP_RANGE,
                ip_range_from=IPv4Address("192.0.2.20"),
                ip_range_to=IPv4Address("192.0.2.30"),
            ),
            "192.0.2.20-192.0.2.30",
        ),
        (
            SdwanAddrObject(
                id=14,
                parents=(),
                name="branch-hosts",
                type=SdwanAddrObjectType.ADDR_GROUP,
                addr_group=14,
            ),
            "ADDR GROUP: branch-hosts",
        ),
    ],
)
def test_sdwan_catalog_index_formats_address_values(
    address_object: SdwanAddrObject,
    expected_value: str,
) -> None:
    entity = SdwanFullCatalogIndex(
        _catalog(address_objects=[address_object])
    ).get_display_entity(
        entity_type=MappingEntityType.ADDR,
        sdwan_entity_id=address_object.id,
    )

    assert entity.name == address_object.name
    assert entity.type == address_object.type
    assert entity.str_value == expected_value


def test_sdwan_catalog_index_formats_zone_and_service_values() -> None:
    service = SdwanService(
        id=20,
        name="web",
        l4_proto=SdwanServiceL4Proto.TCP,
        ranges=((80, 80), (443, 444)),
        codes=None,
    )
    index = SdwanFullCatalogIndex(_catalog(services=[service]))

    zone = index.get_display_entity(
        entity_type=MappingEntityType.ZONE,
        sdwan_entity_id=1,
    )
    service_entity = index.get_display_entity(
        entity_type=MappingEntityType.SERVICE,
        sdwan_entity_id=20,
    )

    assert zone.str_value == "LAN"
    assert service_entity.str_value == "tcp/80,443-444"


@pytest.mark.parametrize(
    "entity_type",
    [MappingEntityType.ZONE, MappingEntityType.ADDR, MappingEntityType.SERVICE],
)
def test_sdwan_catalog_index_rejects_unknown_entity_id(
    entity_type: MappingEntityType,
) -> None:
    index = SdwanFullCatalogIndex(_catalog())

    with pytest.raises(MappingModuleNotFoundError, match="not found"):
        index.get_display_entity(entity_type=entity_type, sdwan_entity_id=999)


def test_canonical_zone_index_rejects_duplicate_ids_and_unknown_lookup() -> None:
    zone_id = uuid4()
    zone = CanonicalZone(id=zone_id, zone_key="inside", name="Inside")

    with pytest.raises(MappingModuleDomainValidationError, match="Duplicate"):
        CanonicalZoneIndex([zone, zone])

    with pytest.raises(MappingModuleNotFoundError, match="not found"):
        CanonicalZoneIndex([zone]).get(uuid4())
