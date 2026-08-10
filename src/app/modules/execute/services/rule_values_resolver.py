import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Protocol, Self, TypeAlias

from app.core.hashers import json_hash
from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.domain.enums import SdwanRuleAction
from app.modules.execute.domain.value_objects import RuleBody


class CoverableMatchableObject(Protocol):
    """Value object that supports exact signatures and coverage checks."""

    def covers(self, other: Self) -> bool: ...

    def signature(self) -> Any: ...


class RuleValueNormalizationError(ValueError):
    """Raised when rule/object values cannot be safely normalized for compare."""


AddressValue: TypeAlias = "AddressSpan | FqdnValue"
MAX_ADDR_GROUP_NESTING_LEVEL = 3


@dataclass(frozen=True, slots=True, order=True)
class AddressSpan(CoverableMatchableObject):
    """Normalized IPv4 value represented as inclusive integer range."""

    start: int
    end: int

    @classmethod
    def from_network(cls, value: str | IPv4Network) -> Self:
        network = value if isinstance(value, IPv4Network) else IPv4Network(value)
        return cls(
            start=int(network.network_address),
            end=int(network.broadcast_address),
        )

    @classmethod
    def from_host(cls, value: str | IPv4Address) -> Self:
        address = value if isinstance(value, IPv4Address) else IPv4Address(value)
        address_as_int = int(address)
        return cls(start=address_as_int, end=address_as_int)

    @classmethod
    def from_range(cls, start: str | IPv4Address, end: str | IPv4Address) -> Self:
        start_ip = start if isinstance(start, IPv4Address) else IPv4Address(start)
        end_ip = end if isinstance(end, IPv4Address) else IPv4Address(end)

        if int(start_ip) > int(end_ip):
            raise RuleValueNormalizationError(
                f"Invalid IPv4 range: start {start} is greater than end {end}"
            )

        return cls(start=int(start_ip), end=int(end_ip))

    def covers(self, other: Self) -> bool:
        """Return true when current range fully covers another IPv4 range."""
        if not isinstance(other, AddressSpan):
            return False
        return self.start <= other.start and self.end >= other.end

    def signature(self) -> tuple[str, int, int]:
        """Stable representation used by exact comparison."""
        return "ipv4", self.start, self.end

    def display(self) -> str:
        """Compact human-readable IPv4 range."""
        if self.start == self.end:
            return str(IPv4Address(self.start))
        return f"{IPv4Address(self.start)}-{IPv4Address(self.end)}"


@dataclass(frozen=True, slots=True, order=True)
class FqdnValue(CoverableMatchableObject):
    """Normalized FQDN value."""

    domain: str

    @classmethod
    def from_raw(cls, value: str) -> Self:
        return cls(domain=value.strip().lower())

    def covers(self, other: AddressValue) -> bool:
        """FQDN covers only the same normalized FQDN string."""
        if not isinstance(other, FqdnValue):
            return False
        return self.domain == other.domain

    def signature(self) -> tuple[str, str]:
        return "fqdn", self.domain

    def display(self) -> str:
        """Compact human-readable FQDN value."""
        return self.domain


@dataclass(frozen=True, slots=True)
class ServiceValue(CoverableMatchableObject):
    """Normalized SD-WAN service value.

    ANY covers every service; TCP/UDP are compared by protocol and port range;
    ICMP is compared by code set; IP_IP is protocol-only and is not treated as ANY.
    """

    proto: SdwanServiceL4Proto
    port_start: int | None = None
    port_end: int | None = None
    codes: frozenset[str] | None = None

    @classmethod
    def any(cls) -> Self:
        return cls(proto=SdwanServiceL4Proto.ANY)

    @classmethod
    def protocol_only(cls, proto: SdwanServiceL4Proto) -> Self:
        """Create service without ports/codes, for example IP_IP."""
        if proto == SdwanServiceL4Proto.ANY:
            return cls.any()
        return cls(proto=proto)

    @classmethod
    def port_range(cls, proto: SdwanServiceL4Proto, start: int, end: int) -> Self:
        if proto not in {SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP}:
            raise RuleValueNormalizationError(
                f"Port range is supported only for TCP/UDP, got {proto}"
            )
        if start < 0 or end > 65535 or start > end:
            raise RuleValueNormalizationError(
                f"Invalid port range for {proto}: {start}-{end}"
            )
        return cls(proto=proto, port_start=start, port_end=end)

    @classmethod
    def icmp(cls, codes: Iterable[str] | None) -> Self:
        normalized_codes = frozenset(_normalize_text(code) for code in (codes or []))
        return cls(proto=SdwanServiceL4Proto.ICMP, codes=normalized_codes)

    def covers(self, other: Self) -> bool:
        """Return true when current service fully covers another service."""
        if self.proto == SdwanServiceL4Proto.ANY:
            return True
        if other.proto == SdwanServiceL4Proto.ANY:
            return False
        if self.proto != other.proto:
            return False
        if self.proto == SdwanServiceL4Proto.ICMP:
            return (self.codes or frozenset()).issuperset(other.codes or frozenset())
        if self.proto in {SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP}:
            return (
                self.port_start <= other.port_start and self.port_end >= other.port_end  # type: ignore[operator]
            )
        if self.proto == SdwanServiceL4Proto.IP_IP:
            return (
                self.port_start is None
                and self.port_end is None
                and other.port_start is None
                and other.port_end is None
                and self.codes is None
                and other.codes is None
            )
        raise RuleValueNormalizationError("Unsupported services comparison")

    def signature(self) -> tuple[Any, ...]:
        return (
            self.proto.value,
            self.port_start,
            self.port_end,
            tuple(sorted(self.codes)) if self.codes is not None else None,
        )

    def display(self) -> str:
        """Compact human-readable service value."""
        if self.proto == SdwanServiceL4Proto.ANY:
            return "any"
        if self.proto in {SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP}:
            if self.port_start == self.port_end:
                return f"{self.proto.value}/{self.port_start}"
            return f"{self.proto.value}/{self.port_start}-{self.port_end}"
        if self.proto == SdwanServiceL4Proto.ICMP:
            return f"icmp/{','.join(sorted(self.codes or frozenset()))}"
        return self.proto.value


@dataclass(frozen=True, slots=True)
class NormalizedRuleValues:
    """Rule normalized for exact and coverage comparison."""

    action: SdwanRuleAction
    src_zones: frozenset[str]
    dst_zones: frozenset[str]
    src_addresses: frozenset[AddressValue]
    dst_addresses: frozenset[AddressValue]
    services: frozenset[ServiceValue]

    def exact_signature(self) -> str:
        """Stable full-rule signature used for exact matching."""
        payload = {
            "action": self.action.value,
            "src_zones": sorted(self.src_zones),
            "dst_zones": sorted(self.dst_zones),
            "src_addresses": _sorted_signatures(self.src_addresses),
            "dst_addresses": _sorted_signatures(self.dst_addresses),
            "services": _sorted_signatures(self.services),
        }
        return json_hash(payload)

    def covers(self, other: Self) -> bool:
        """Return true when existing SD-WAN values cover planned rule values."""
        return (
            self.action == other.action
            and _str_set_covers(self.src_zones, other.src_zones)
            and _str_set_covers(self.dst_zones, other.dst_zones)
            and _values_cover_all(self.src_addresses, other.src_addresses)
            and _values_cover_all(self.dst_addresses, other.dst_addresses)
            and _values_cover_all(self.services, other.services)
        )


class RuleValuesResolver:
    """Normalize RuleBody values through already loaded SD-WAN catalog objects.

    The resolver expects address groups to be expanded by SDWANCatalogGateway.
    It still walks parent-child links at normalization time to replace group ids
    with leaf address values used for exact/coverage comparison.
    """

    def __init__(
        self,
        *,
        zones: list[SdwanZone],
        services: list[SdwanService],
        address_objects: list[SdwanAddrObject],
    ) -> None:
        self._zones_by_id: dict[int, SdwanZone] = {zone.id: zone for zone in zones}
        self._services_by_id: dict[int, SdwanService] = {
            int(service.id): service for service in services
        }
        self._addr_objects_by_id: dict[int, SdwanAddrObject] = {
            int(addr_obj.id): addr_obj for addr_obj in address_objects
        }

        self._addr_children_by_parent: dict[int, list[SdwanAddrObject]] = defaultdict(
            list
        )
        for addr_obj in address_objects:
            for parent_id in addr_obj.parents:
                self._addr_children_by_parent[int(parent_id)].append(addr_obj)

    def normalize_rule(self, rule: RuleBody) -> NormalizedRuleValues:
        """Normalize planned or existing SD-WAN rule body."""
        return NormalizedRuleValues(
            action=self._normalize_action(rule.action),
            src_zones=self._normalize_zones(rule.src_zones),
            dst_zones=self._normalize_zones(rule.dst_zones),
            src_addresses=self._normalize_addresses(rule.src_addr_objects),
            dst_addresses=self._normalize_addresses(rule.dst_addr_objects),
            services=self._normalize_services(rule.services),
        )

    def _normalize_action(self, action: SdwanRuleAction) -> SdwanRuleAction:
        if action in (SdwanRuleAction.REJECT, SdwanRuleAction.DROP):
            return SdwanRuleAction.REJECT
        return SdwanRuleAction.ACCEPT

    def _normalize_zones(self, zone_ids: Iterable[int]) -> frozenset[str]:
        values: set[str] = set()
        for zone_id in zone_ids:
            zone = self._zones_by_id.get(zone_id)
            if not zone:
                raise RuleValueNormalizationError(f"Unknown zone id: {zone_id}")
            values.add(_normalize_text(zone.name))
        return frozenset(values)

    def _normalize_addresses(
        self,
        addr_object_ids: Iterable[int],
    ) -> frozenset[AddressValue]:
        values: set[AddressValue] = set()
        for addr_object_id in addr_object_ids:
            values.update(
                self._address_values_for_id(
                    addr_object_id=addr_object_id,
                    current_group_level=0,
                )
            )
        return frozenset(values)

    def _address_values_for_id(
        self,
        addr_object_id: int,
        *,
        current_group_level: int,
    ) -> list[AddressValue]:
        addr_obj = self._addr_objects_by_id.get(addr_object_id)
        if not addr_obj:
            raise RuleValueNormalizationError(
                f"Unknown address object id: {addr_object_id}"
            )
        if addr_obj.type == SdwanAddrObjectType.ADDR_GROUP:
            return self._address_values_from_group(
                addr_group_obj=addr_obj,
                group_level=current_group_level + 1,
            )
        return [self._address_value_from_leaf(addr_obj)]

    def _address_values_from_group(
        self,
        addr_group_obj: SdwanAddrObject,
        *,
        group_level: int,
    ) -> list[AddressValue]:
        if group_level > MAX_ADDR_GROUP_NESTING_LEVEL:
            raise RuleValueNormalizationError(
                f"Address group nesting level exceeded: "
                f"group object id={addr_group_obj.id}, "
                f"group value={addr_group_obj.addr_group}, "
                f"level={group_level}, "
                f"max_level={MAX_ADDR_GROUP_NESTING_LEVEL}"
            )

        group_id = addr_group_obj.addr_group or addr_group_obj.id
        children: list[SdwanAddrObject] = self._addr_children_by_parent.get(
            int(group_id), []
        )
        if not children:
            raise RuleValueNormalizationError(
                f"Address group {group_id} has no loaded children"
            )

        result: list[AddressValue] = []
        for child in children:
            if child.id == addr_group_obj.id:
                continue
            result.extend(
                self._address_values_for_id(
                    addr_object_id=child.id,
                    current_group_level=group_level,
                )
            )

        if not result:
            raise RuleValueNormalizationError(
                f"Address group {addr_group_obj.id} has no leaf children"
            )
        return result

    def _address_value_from_leaf(self, addr_obj: SdwanAddrObject) -> AddressValue:
        match addr_obj.type:
            case SdwanAddrObjectType.PREFIX:
                if addr_obj.prefix is None:
                    raise RuleValueNormalizationError(
                        f"Prefix address object {addr_obj.id} has no prefix value"
                    )
                return AddressSpan.from_network(addr_obj.prefix)

            case SdwanAddrObjectType.NETWORK:
                if addr_obj.network is None:
                    raise RuleValueNormalizationError(
                        f"Network address object {addr_obj.id} has no resolved network value"
                    )
                return AddressSpan.from_network(addr_obj.network)

            case SdwanAddrObjectType.HOST:
                if addr_obj.host is None:
                    raise RuleValueNormalizationError(
                        f"Host address object {addr_obj.id} has no host value"
                    )
                return AddressSpan.from_host(addr_obj.host)

            case SdwanAddrObjectType.IP_RANGE:
                if addr_obj.ip_range_from is None or addr_obj.ip_range_to is None:
                    raise RuleValueNormalizationError(
                        f"IP range address object {addr_obj.id} has incomplete range"
                    )
                return AddressSpan.from_range(
                    start=addr_obj.ip_range_from,
                    end=addr_obj.ip_range_to,
                )

            case SdwanAddrObjectType.FQDN:
                if addr_obj.fqdn is None:
                    raise RuleValueNormalizationError(
                        f"FQDN address object {addr_obj.id} has no fqdn value"
                    )
                return FqdnValue.from_raw(addr_obj.fqdn)

            case SdwanAddrObjectType.ADDR_GROUP:
                raise RuleValueNormalizationError(
                    "ADDR_GROUP must be expanded before leaf normalization"
                )

            case _:
                raise RuleValueNormalizationError(
                    f"Unsupported address object type for value comparison: {addr_obj.type}"
                )

    def _normalize_services(
        self, service_ids: Iterable[int]
    ) -> frozenset[ServiceValue]:
        values: list[ServiceValue] = []
        for service_id in service_ids:
            values.extend(self._service_values_for_id(int(service_id)))
        return frozenset(values)

    def _service_values_for_id(self, service_id: int) -> list[ServiceValue]:
        service: SdwanService | None = self._services_by_id.get(service_id)
        if not service:
            raise RuleValueNormalizationError(f"Unknown service id: {service_id}")

        match service.l4_proto:
            case SdwanServiceL4Proto.TCP | SdwanServiceL4Proto.UDP:
                if not service.ranges:
                    raise RuleValueNormalizationError(
                        f"TCP/UDP service {service_id} has no port ranges"
                    )
                return [
                    ServiceValue.port_range(
                        proto=service.l4_proto,
                        start=range_[0],
                        end=range_[1],
                    )
                    for range_ in service.ranges
                ]

            case SdwanServiceL4Proto.ICMP:
                return [ServiceValue.icmp(service.codes)]

            case SdwanServiceL4Proto.ANY:
                return [ServiceValue.any()]

            case SdwanServiceL4Proto.IP_IP:
                return [ServiceValue.protocol_only(SdwanServiceL4Proto.IP_IP)]

            case _:
                raise RuleValueNormalizationError(
                    f"Unsupported service l4_proto: {service.l4_proto}"
                )


def _normalize_text(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r"[\s_-]+", "-", value)


def _sorted_signatures(values: Iterable[CoverableMatchableObject]) -> list[Any]:
    return sorted((value.signature() for value in values), key=repr)


def _str_set_covers(existing: frozenset[str], target: frozenset[str]) -> bool:
    if not target:
        return not existing
    if not existing:
        return False
    return existing.issuperset(target)


def _values_cover_all(
    existing: frozenset[CoverableMatchableObject],
    target: frozenset[CoverableMatchableObject],
) -> bool:
    if not target:
        return not existing
    if not existing:
        return False
    return all(
        any(existing_value.covers(target_value) for existing_value in existing)
        for target_value in target
    )
