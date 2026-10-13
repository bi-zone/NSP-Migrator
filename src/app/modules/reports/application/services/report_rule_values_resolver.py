from collections.abc import Iterable
from typing import TYPE_CHECKING

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
    SdwanFullCatalog,
    SdwanService,
)
from app.modules.reports.domain.value_objects import ReportRuleSnapshot

if TYPE_CHECKING:
    from app.modules.reports.application.use_cases.save_report import (
        SaveReportRuleCommand,
    )


class ReportRuleValuesResolver:
    """Resolve Execute rule IDs into historical values without failing a report."""

    def __init__(self, catalog: SdwanFullCatalog) -> None:
        self._zones_by_id = {zone.id: zone for zone in catalog.zones}
        self._services_by_id = {service.id: service for service in catalog.services}
        self._address_group_resolver = SDWANAddressGroupLeavesResolver(
            catalog.addr_objs
        )

    def resolve(self, rule: "SaveReportRuleCommand") -> ReportRuleSnapshot:
        return ReportRuleSnapshot(
            policy_name=rule.policy_name,
            action=rule.action,
            priority=rule.priority,
            src_zone_names=self._resolve_zone_names(rule.src_zone_ids),
            dst_zone_names=self._resolve_zone_names(rule.dst_zone_ids),
            src_addr_values=self._resolve_address_values(rule.src_addr_object_ids),
            dst_addr_values=self._resolve_address_values(rule.dst_addr_object_ids),
            service_values=self._resolve_service_values(rule.service_ids),
            migration_result=rule.migration_result,
            reason=rule.reason,
        )

    def _resolve_zone_names(self, ids: Iterable[int]) -> tuple[str, ...]:
        values: list[str] = []
        for zone_id in ids:
            zone = self._zones_by_id.get(zone_id)
            if zone is not None:
                values.append(zone.name)
        return tuple(values)

    def _resolve_address_values(self, ids: Iterable[int]) -> tuple[str, ...]:
        values: list[str] = []
        for address_object_id in ids:
            try:
                leaf_objects = self._address_group_resolver.resolve_leaves(
                    address_object_id
                )
            except SDWANAddressGroupResolutionError:
                continue

            values.extend(
                value
                for address_object in leaf_objects
                if (value := _address_value(address_object)) is not None
            )
        return tuple(values)

    def _resolve_service_values(self, ids: Iterable[int]) -> tuple[str, ...]:
        values: list[str] = []
        for service_id in ids:
            service = self._services_by_id.get(service_id)
            if service is not None:
                values.extend(_service_values(service))
        return tuple(values)


def _address_value(address_object: SdwanAddrObject) -> str | None:
    match address_object.type:
        case SdwanAddrObjectType.PREFIX:
            return str(address_object.prefix)
        case SdwanAddrObjectType.NETWORK:
            return str(address_object.network)
        case SdwanAddrObjectType.HOST:
            return str(address_object.host) if address_object.host is not None else None
        case SdwanAddrObjectType.IP_RANGE:
            if (
                address_object.ip_range_from is None
                or address_object.ip_range_to is None
            ):
                return None
            return f"{address_object.ip_range_from}-{address_object.ip_range_to}"
        case SdwanAddrObjectType.FQDN:
            return address_object.fqdn.strip().lower() if address_object.fqdn else None
        case SdwanAddrObjectType.ADDR_GROUP:
            return None
        case _:
            return None


def _service_values(service: SdwanService) -> tuple[str, ...]:
    match service.l4_proto:
        case SdwanServiceL4Proto.TCP | SdwanServiceL4Proto.UDP:
            if service.ranges is None:
                return ()
            return tuple(
                (
                    f"{service.l4_proto.value}/{start}"
                    if start == end
                    else f"{service.l4_proto.value}/{start}-{end}"
                )
                for start, end in service.ranges
            )
        case SdwanServiceL4Proto.ICMP:
            return (f"icmp/{','.join(sorted(service.codes or ()))}",)
        case SdwanServiceL4Proto.ANY:
            return ("any",)
        case SdwanServiceL4Proto.IP_IP:
            return (service.l4_proto.value,)
        case _:
            return ()
