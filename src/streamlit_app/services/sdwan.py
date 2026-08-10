from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)

SdwanEntity = SdwanZone | SdwanAddrObject | SdwanService


def sdwan_item_str_value(item: SdwanEntity) -> str:  # noqa

    if isinstance(item, SdwanZone):
        return item.name

    elif isinstance(item, SdwanAddrObject):
        if item.type == SdwanAddrObjectType.NETWORK:
            return str(item.network)

        if item.type == SdwanAddrObjectType.PREFIX:
            return str(item.prefix)

        if item.type == SdwanAddrObjectType.HOST:
            return str(item.host)

        if item.type == SdwanAddrObjectType.FQDN:
            return item.fqdn  # type: ignore

        if item.type == SdwanAddrObjectType.IP_RANGE:
            return f"{item.ip_range_from}-{item.ip_range_to}"

        if item.type == SdwanAddrObjectType.ADDR_GROUP:
            return f"ADDR GROUP: {item.name}"

        return item.name

    elif isinstance(item, SdwanService):
        if item.ranges:
            ranges = ",".join(
                str(port_from) if port_from == port_to else f"{port_from}-{port_to}"
                for port_from, port_to in item.ranges
            )
            return f"{item.l4_proto}/{ranges}"

        if item.codes:
            return f"{item.l4_proto}/{','.join(item.codes)}"

        return item.l4_proto.value

    else:
        raise ValueError(f"Unexpected sdwan item type: {type(item)}")
