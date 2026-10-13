from dataclasses import dataclass
from ipaddress import IPv4Address

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from streamlit_app.services.sdwan import sdwan_item_str_value


def test_sdwan_item_str_value_formats_current_catalog_models() -> None:
    assert (
        sdwan_item_str_value(
            SdwanZone(id=1, zone_id=10, name="LAN", type=SdwanZoneType.LAN)
        )
        == "LAN"
    )
    assert (
        sdwan_item_str_value(
            SdwanAddrObject(
                id=2,
                parents=(),
                name="host-1",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("192.0.2.10"),
            )
        )
        == "192.0.2.10"
    )
    assert (
        sdwan_item_str_value(
            SdwanService(
                id=3,
                name="https",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((443, 443),),
                codes=None,
            )
        )
        == "tcp/443"
    )


def test_sdwan_item_str_value_formats_catalog_models_from_before_hot_reload() -> None:

    stale_zone = SdwanZone(id=1, zone_id=10, name="LAN", type=SdwanZoneType.LAN)

    assert sdwan_item_str_value(stale_zone) == "LAN"  # type: ignore[arg-type]


def test_sdwan_item_str_value_rejects_unknown_models() -> None:
    with pytest.raises(ValueError, match="Unexpected sdwan item type"):
        sdwan_item_str_value(object())  # type: ignore[arg-type]
