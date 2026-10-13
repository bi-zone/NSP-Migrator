from typing import Any

from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)

SdwanEntity = SdwanZone | SdwanAddrObject | SdwanService


def sdwan_item_str_value(item: SdwanEntity) -> str:
    """Format a catalog item retained in Streamlit session state.

    Streamlit may reload this module while session state still contains model
    objects instantiated by the previous module version.  Dispatching by the
    stable model name keeps those objects readable across the reload boundary.
    """

    if isinstance(item, SdwanZone):
        return str(getattr(item, "name"))

    elif isinstance(item, SdwanAddrObject):
        return _format_sdwan_addr_object(item)

    elif isinstance(item, SdwanService):
        return _format_sdwan_service(item)

    raise ValueError(f"Unexpected sdwan item type: {type(item)}")


def _format_sdwan_addr_object(item: Any) -> str:
    item_type = getattr(item, "type")
    item_type_value = getattr(item_type, "value", item_type)

    if item_type_value == SdwanAddrObjectType.NETWORK.value:
        return str(getattr(item, "network"))

    if item_type_value == SdwanAddrObjectType.PREFIX.value:
        return str(getattr(item, "prefix"))

    if item_type_value == SdwanAddrObjectType.HOST.value:
        return str(getattr(item, "host"))

    if item_type_value == SdwanAddrObjectType.FQDN.value:
        return str(getattr(item, "fqdn"))

    if item_type_value == SdwanAddrObjectType.IP_RANGE.value:
        return f"{getattr(item, 'ip_range_from')}-{getattr(item, 'ip_range_to')}"

    if item_type_value == SdwanAddrObjectType.ADDR_GROUP.value:
        return f"ADDR GROUP: {getattr(item, 'name')}"

    return str(getattr(item, "name"))


def _format_sdwan_service(item: Any) -> str:
    ranges = getattr(item, "ranges")
    if ranges:
        ranges_str = ",".join(
            str(port_from) if port_from == port_to else f"{port_from}-{port_to}"
            for port_from, port_to in ranges
        )
        return f"{getattr(item, 'l4_proto')}/{ranges_str}"

    codes = getattr(item, "codes")
    if codes:
        return f"{getattr(item, 'l4_proto')}/{','.join(codes)}"

    l4_proto = getattr(item, "l4_proto")
    return str(getattr(l4_proto, "value", l4_proto))
