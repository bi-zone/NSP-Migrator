import re
from collections.abc import Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Generic, Protocol, Self, TypeAlias, TypeVar

from app.core.hashers import json_hash
from app.integrations.sdwan_csp_api.gateways.address_group_resolver import (
    SDWANAddressGroupLeavesResolver,
    SDWANAddressGroupResolutionError,
)
from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.domain.enums import CoverageField, SdwanRuleAction
from app.modules.execute.domain.value_objects import (
    CoverageDetail,
    CoverageValue,
    RuleBody,
)


class CoverableMatchableObject(Protocol):
    """Value object that supports exact signatures and coverage checks."""

    def covers(self, other: Self) -> bool: ...

    def signature(self) -> Any: ...


class RuleValueNormalizationError(ValueError):
    """Raised when rule/object values cannot be safely normalized for compare."""


AddressValue: TypeAlias = "AddressSpan | FqdnValue"
CoverableValue = TypeVar("CoverableValue", bound=CoverableMatchableObject)


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
class _ResolvedCoverageValue(Generic[CoverableValue]):
    """Normalized value and the concrete SD-WAN object that provides it."""

    value: CoverableValue
    evidence: CoverageValue


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


@dataclass(frozen=True, slots=True)
class ResolvedRuleValues:
    """Normalized rule values with source objects retained for coverage evidence."""

    normalized: NormalizedRuleValues
    src_addresses: tuple[_ResolvedCoverageValue[AddressValue], ...]
    dst_addresses: tuple[_ResolvedCoverageValue[AddressValue], ...]
    services: tuple[_ResolvedCoverageValue[ServiceValue], ...]

    def exact_signature(self) -> str:
        """Return the signature of the normalized rule values."""
        return self.normalized.exact_signature()


@dataclass(frozen=True, slots=True)
class CoverageAnalysis:
    """Result of one existing-to-planned coverage comparison."""

    is_covered: bool
    details: tuple[CoverageDetail, ...] = ()


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
        self._address_group_resolver = SDWANAddressGroupLeavesResolver(
            address_objects,
        )

    def resolve_rule(self, rule: RuleBody) -> ResolvedRuleValues:
        """Resolve one rule once for exact comparison and coverage evidence."""
        src_addresses = self._resolve_address_values(rule.src_addr_objects)
        dst_addresses = self._resolve_address_values(rule.dst_addr_objects)
        services = self._resolve_service_values(rule.services)

        return ResolvedRuleValues(
            normalized=NormalizedRuleValues(
                action=self._normalize_action(rule.action),
                src_zones=self._normalize_zones(rule.src_zones),
                dst_zones=self._normalize_zones(rule.dst_zones),
                src_addresses=frozenset(item.value for item in src_addresses),
                dst_addresses=frozenset(item.value for item in dst_addresses),
                services=frozenset(item.value for item in services),
            ),
            src_addresses=src_addresses,
            dst_addresses=dst_addresses,
            services=services,
        )

    def analyze_coverage(
        self,
        *,
        existing: ResolvedRuleValues,
        planned: ResolvedRuleValues,
    ) -> CoverageAnalysis:
        """Determine coverage and return only its strict object-value deltas."""
        existing_normalized = existing.normalized
        planned_normalized = planned.normalized
        if (
            existing_normalized.action != planned_normalized.action
            or not _str_set_covers(
                existing_normalized.src_zones,
                planned_normalized.src_zones,
            )
            or not _str_set_covers(
                existing_normalized.dst_zones,
                planned_normalized.dst_zones,
            )
        ):
            return CoverageAnalysis(is_covered=False)

        src_details = self._analyze_values_coverage(
            field=CoverageField.SRC_ADDR_OBJECTS,
            existing_values=existing.src_addresses,
            planned_values=planned.src_addresses,
        )
        if src_details is None:
            return CoverageAnalysis(is_covered=False)

        dst_details = self._analyze_values_coverage(
            field=CoverageField.DST_ADDR_OBJECTS,
            existing_values=existing.dst_addresses,
            planned_values=planned.dst_addresses,
        )
        if dst_details is None:
            return CoverageAnalysis(is_covered=False)

        service_details = self._analyze_values_coverage(
            field=CoverageField.SERVICES,
            existing_values=existing.services,
            planned_values=planned.services,
        )
        if service_details is None:
            return CoverageAnalysis(is_covered=False)

        return CoverageAnalysis(
            is_covered=True,
            details=(*src_details, *dst_details, *service_details),
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

    def _resolve_address_values(
        self,
        addr_object_ids: Iterable[int],
    ) -> tuple[_ResolvedCoverageValue[AddressValue], ...]:
        values: list[_ResolvedCoverageValue[AddressValue]] = []
        for addr_object_id in addr_object_ids:
            try:
                leaf_objects = self._address_group_resolver.resolve_leaves(
                    addr_object_id
                )
            except SDWANAddressGroupResolutionError as exc:
                raise RuleValueNormalizationError(str(exc)) from None

            values.extend(
                self._resolved_address_value(address_object=address_object)
                for address_object in leaf_objects
            )
        return _distinct_resolved_values(values)

    def _resolved_address_value(
        self,
        *,
        address_object: SdwanAddrObject,
    ) -> _ResolvedCoverageValue[AddressValue]:
        value = self._address_value_from_leaf(address_object)
        return _ResolvedCoverageValue(
            value=value,
            evidence=CoverageValue(
                object_id=address_object.id,
                object_name=address_object.name,
                value=value.display(),
            ),
        )

    def _address_value_from_leaf(self, addr_obj: SdwanAddrObject) -> AddressValue:  # noqa
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

    def _resolve_service_values(
        self,
        service_ids: Iterable[int],
    ) -> tuple[_ResolvedCoverageValue[ServiceValue], ...]:
        values: list[_ResolvedCoverageValue[ServiceValue]] = []
        for service_id in service_ids:
            service = self._services_by_id.get(int(service_id))
            if not service:
                raise RuleValueNormalizationError(f"Unknown service id: {service_id}")
            for value in self._service_values_for_id(int(service_id)):
                values.append(
                    _ResolvedCoverageValue(
                        value=value,
                        evidence=CoverageValue(
                            object_id=int(service.id),
                            object_name=service.name,
                            value=value.display(),
                        ),
                    )
                )
        return _distinct_resolved_values(values)

    @staticmethod
    def _analyze_values_coverage(
        *,
        field: CoverageField,
        existing_values: tuple[_ResolvedCoverageValue[CoverableValue], ...],
        planned_values: tuple[_ResolvedCoverageValue[CoverableValue], ...],
    ) -> tuple[CoverageDetail, ...] | None:
        if not planned_values:
            return () if not existing_values else None
        if not existing_values:
            return None

        covered_by_existing: dict[CoverageValue, list[CoverageValue]] = {}

        for planned in planned_values:
            covering = next(
                (
                    existing
                    for existing in existing_values
                    if existing.value.covers(planned.value)
                ),
                None,
            )
            if covering is None:
                return None
            if covering.value.signature() != planned.value.signature():
                covered_by_existing.setdefault(covering.evidence, []).append(
                    planned.evidence
                )

        return tuple(
            CoverageDetail(
                field=field,
                covering_value=covering_value,
                covered_values=tuple(covered_values),
            )
            for covering_value, covered_values in covered_by_existing.items()
        )

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


def _distinct_resolved_values(  # noqa
    values: Iterable[_ResolvedCoverageValue[CoverableValue]],
) -> tuple[_ResolvedCoverageValue[CoverableValue], ...]:
    """Keep the first object for each semantic value used by set comparison."""
    unique_values: dict[Any, _ResolvedCoverageValue[CoverableValue]] = {}
    for resolved_value in values:
        unique_values.setdefault(resolved_value.value.signature(), resolved_value)
    return tuple(unique_values.values())


def _str_set_covers(existing: frozenset[str], target: frozenset[str]) -> bool:
    if not target:
        return not existing
    if not existing:
        return False
    return existing.issuperset(target)
