from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from app.core.hashers import json_hash
from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanDeviceObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)


@dataclass(slots=True, frozen=True)
class SdwanZone:
    id: int
    zone_id: int
    name: str
    type: SdwanZoneType


@dataclass(slots=True, frozen=True)
class SdwanService:
    id: int
    name: str
    l4_proto: SdwanServiceL4Proto
    ranges: tuple[tuple[int, int], ...] | None  # for tcp, udp
    codes: tuple[str, ...] | None  # for icmp only

    def __post_init__(self):
        if (
            self.l4_proto in (SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP)
            and not self.ranges
        ):
            raise ValueError("TCP/UDP addr obj must have ranges")

        if self.l4_proto == SdwanServiceL4Proto.ICMP and not self.codes:
            raise ValueError("ICMP addr obj must have codes")


@dataclass(slots=True, frozen=True)
class SdwanAddrObject:
    """
    Address object for domain logic using

    Values examples:
    - Type: PREFIX, Value: "10.10.10.0/24"
    - Type: HOST, Value: "10.10.10.10"
    - Type: FQDN, Value: "domain.com"
    - Type: IP_RANGE, Value: "10.10.10.10-10.10.10.20"
    - Type: NETWORK (PREFIX analog), Value: "10.10.10.0/24"
    - Type: ADDR_GROUP, Value: "42" - sdwan addr-group ID
    """

    id: int
    parents: tuple[int, ...]
    name: str
    type: SdwanAddrObjectType

    network_id: str | None = None  # for NETWORK type
    network: IPv4Network | None = None  # for NETWORK type (PREFIX analog)

    prefix: IPv4Network | None = None  # for PREFIX type
    host: IPv4Address | None = None  # for HOST type
    fqdn: str | None = None  # for FQDN type

    ip_range_from: IPv4Address | None = None  # for IP_RANGE type
    ip_range_to: IPv4Address | None = None

    addr_group: int | None = (
        None  # for ADDR_GROUP type - Addr Group ID (equals id field)
    )

    def __post_init__(self):

        if self.type == SdwanAddrObjectType.NETWORK and (
            self.network_id is None or self.network is None
        ):
            raise ValueError("Network addr obj must have network net and network_id")

        if self.type == SdwanAddrObjectType.PREFIX and self.prefix is None:
            raise ValueError("Prefix addr obj must have prefix net")

        if self.type == SdwanAddrObjectType.HOST and self.host is None:
            raise ValueError("Host addr obj must have host address")

        if self.type == SdwanAddrObjectType.FQDN and self.fqdn is None:
            raise ValueError("FQDN addr obj must have fqdn string")

        if self.type == SdwanAddrObjectType.IP_RANGE and (
            self.ip_range_from is None or self.ip_range_to is None
        ):
            raise ValueError("IP Range addr obj must have from and to values")


@dataclass(slots=True, frozen=True)
class SdwanNetwork:
    """Network (sub-entity for SdwanAddrObject if type is Network)"""

    network_id: str
    net: IPv4Network


@dataclass(slots=True, frozen=True)
class SdwanFullCatalog:
    zones: list[SdwanZone]
    services: list[SdwanService]
    addr_objs: list[SdwanAddrObject]
    networks: list[SdwanNetwork]

    def get_fingerprint(self) -> str:
        """Return an order-independent fingerprint of this full SD-WAN catalog."""
        return json_hash(
            {
                "zones": [
                    {
                        "id": zone.id,
                        "zone_id": zone.zone_id,
                        "name": zone.name,
                        "type": zone.type.value,
                    }
                    for zone in self.zones
                ],
                "services": [
                    {
                        "id": service.id,
                        "name": service.name,
                        "l4_proto": service.l4_proto.value,
                        "ranges": (
                            [list(range_) for range_ in service.ranges]
                            if service.ranges is not None
                            else None
                        ),
                        "codes": (
                            list(service.codes) if service.codes is not None else None
                        ),
                    }
                    for service in self.services
                ],
                "addr_objects": [
                    {
                        "id": addr_obj.id,
                        "parents": list(addr_obj.parents),
                        "name": addr_obj.name,
                        "type": addr_obj.type.value,
                        "network_id": addr_obj.network_id,
                        "network": str(addr_obj.network) if addr_obj.network else None,
                        "prefix": str(addr_obj.prefix) if addr_obj.prefix else None,
                        "host": str(addr_obj.host) if addr_obj.host else None,
                        "fqdn": addr_obj.fqdn,
                        "ip_range_from": (
                            str(addr_obj.ip_range_from)
                            if addr_obj.ip_range_from
                            else None
                        ),
                        "ip_range_to": (
                            str(addr_obj.ip_range_to) if addr_obj.ip_range_to else None
                        ),
                        "addr_group": addr_obj.addr_group,
                    }
                    for addr_obj in self.addr_objs
                ],
                "networks": [
                    {
                        "network_id": network.network_id,
                        "net": str(network.net),
                    }
                    for network in self.networks
                ],
            }
        )


@dataclass(slots=True, frozen=True)
class SdwanDeviceObject:
    dev_obj_id: str
    name: str
    type: SdwanDeviceObjectType
    cpe_id: str | None

    def __post_init__(self):

        if self.type == SdwanDeviceObjectType.GROUP and self.cpe_id is not None:
            raise ValueError("Device Group can't have cpe_id")

        if self.type == SdwanDeviceObjectType.DEVICE and self.cpe_id is None:
            raise ValueError("Device must have cpe_id")
