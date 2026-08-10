from dataclasses import dataclass

from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
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


@dataclass(frozen=True, slots=True)
class SdwanEntityDTO:
    """
    SD-WAN entity summary.
    """

    sdwan_id: int
    name: str
    type: str
    str_value: str


class SdwanFullCatalogIndex:
    """Sdwan catalog index of zones, addr objects, services
    that can provide display view of sd-wan entity (used for projection"""

    def __init__(self, catalog: SdwanFullCatalog) -> None:
        self._zones_by_id: dict[int, SdwanZone] = {}
        self._addr_objs_by_id: dict[int, SdwanAddrObject] = {}
        self._services_by_id: dict[int, SdwanService] = {}

        for zone in catalog.zones:
            if zone.id in self._zones_by_id:
                continue

            self._zones_by_id[zone.id] = zone

        for addr_obj in catalog.addr_objs:
            if addr_obj.id in self._addr_objs_by_id:
                continue

            self._addr_objs_by_id[addr_obj.id] = addr_obj

        for service in catalog.services:
            if service.id in self._services_by_id:
                continue

            self._services_by_id[service.id] = service

    def get_display_entity(
        self,
        *,
        entity_type: MappingEntityType,
        sdwan_entity_id: int,
    ) -> SdwanEntityDTO:
        if entity_type == MappingEntityType.ZONE:
            return self._get_zone_display(sdwan_entity_id)

        if entity_type == MappingEntityType.ADDR:
            return self._get_addr_display(sdwan_entity_id)

        if entity_type == MappingEntityType.SERVICE:
            return self._get_service_display(sdwan_entity_id)

        raise MappingModuleDomainValidationError(
            f"Unsupported SD-WAN entity type: {entity_type}"
        )

    def _get_zone_display(self, zone_id: int) -> SdwanEntityDTO:
        zone = self._zones_by_id.get(zone_id)

        if zone is None:
            raise MappingModuleNotFoundError(f"SD-WAN zone not found: {zone_id}")

        return SdwanEntityDTO(
            sdwan_id=zone.id,
            name=zone.name,
            type=zone.type,
            str_value=zone.name,
        )

    def _get_addr_display(self, addr_obj_id: int) -> SdwanEntityDTO:
        obj = self._addr_objs_by_id.get(addr_obj_id)

        if obj is None:
            raise MappingModuleNotFoundError(
                f"SD-WAN address object not found: {addr_obj_id}"
            )

        return SdwanEntityDTO(
            sdwan_id=obj.id,
            name=obj.name,
            type=obj.type,
            str_value=self._build_addr_str_value(obj),
        )

    def _get_service_display(self, service_id: int) -> SdwanEntityDTO:
        service = self._services_by_id.get(service_id)

        if service is None:
            raise MappingModuleNotFoundError(f"SD-WAN service not found: {service_id}")

        return SdwanEntityDTO(
            sdwan_id=service.id,
            name=service.name,
            type=service.l4_proto,
            str_value=self._build_service_str_value(service),
        )

    @staticmethod
    def _build_addr_str_value(obj: SdwanAddrObject) -> str:
        if obj.type == SdwanAddrObjectType.NETWORK:
            return str(obj.network)

        if obj.type == SdwanAddrObjectType.PREFIX:
            return str(obj.prefix)

        if obj.type == SdwanAddrObjectType.HOST:
            return str(obj.host)

        if obj.type == SdwanAddrObjectType.FQDN:
            return obj.fqdn or obj.name

        if obj.type == SdwanAddrObjectType.IP_RANGE:
            return f"{obj.ip_range_from}-{obj.ip_range_to}"

        if obj.type == SdwanAddrObjectType.ADDR_GROUP:
            return f"ADDR GROUP: {obj.name}"

        return obj.name

    @classmethod
    def _build_service_str_value(cls, service: SdwanService) -> str:

        if service.ranges:
            ranges = ",".join(
                str(port_from) if port_from == port_to else f"{port_from}-{port_to}"
                for port_from, port_to in service.ranges
            )
            return f"{service.l4_proto}/{ranges}"

        if service.codes:
            return f"{service.l4_proto}/{','.join(service.codes)}"

        return service.name
