from dataclasses import replace

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanFullCatalog,
    SdwanService,
    SdwanZone,
)


def _catalog() -> SdwanFullCatalog:
    return SdwanFullCatalog(
        zones=[
            SdwanZone(id=2, zone_id=20, name="WAN", type=SdwanZoneType.WAN),
            SdwanZone(id=1, zone_id=10, name="LAN", type=SdwanZoneType.LAN),
        ],
        services=[
            SdwanService(
                id=200,
                name="dns-tcp",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((53, 53),),
                codes=None,
            ),
            SdwanService(
                id=100,
                name="any",
                l4_proto=SdwanServiceL4Proto.ANY,
                ranges=None,
                codes=None,
            ),
        ],
        addr_objs=[],
        networks=[],
    )


def test_full_catalog_fingerprint_is_independent_of_response_order() -> None:
    catalog = _catalog()
    reordered = replace(
        catalog,
        zones=list(reversed(catalog.zones)),
        services=list(reversed(catalog.services)),
    )

    assert catalog.get_fingerprint() == reordered.get_fingerprint()


def test_full_catalog_fingerprint_changes_when_catalog_value_changes() -> None:
    catalog = _catalog()
    changed_zone = replace(catalog.zones[0], name="INTERNET")
    changed_catalog = replace(catalog, zones=[changed_zone, *catalog.zones[1:]])

    assert catalog.get_fingerprint() != changed_catalog.get_fingerprint()
