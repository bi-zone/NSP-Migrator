from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

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
