from typing import Protocol

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanDeviceObject,
    SdwanFullCatalog,
    SdwanNetwork,
    SdwanService,
    SdwanZone,
)
from app.modules.mapping.domain.value_objects import (
    CreateAddrObjectPayload,
    CreateServicePayload,
)


class MappingSDWANGatewayPort(Protocol):
    """Порт, которым пользуется бизнес‑логика mapping модуля."""

    async def health_check(self) -> None: ...

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog: ...

    async def get_zones(self) -> list[SdwanZone]: ...

    async def get_services(self) -> list[SdwanService]: ...

    async def get_addr_objects(self) -> list[SdwanAddrObject]: ...

    async def get_networks(self) -> list[SdwanNetwork]: ...

    async def get_zone(self, zone_id: int) -> SdwanZone | None: ...

    async def get_service(self, service_id: int) -> SdwanService | None: ...

    async def get_addr_object(self, addr_obj_id: int) -> SdwanAddrObject | None: ...

    async def create_addr_objects_bulk(
        self, payloads: list[CreateAddrObjectPayload]
    ) -> list[int]: ...

    async def create_addr_object(
        self, payload: CreateAddrObjectPayload
    ) -> SdwanAddrObject: ...

    async def create_service(self, payload: CreateServicePayload) -> SdwanService: ...

    async def get_device_objects(self) -> list[SdwanDeviceObject]: ...

    async def get_device_object(self, dev_obj_id: str) -> SdwanDeviceObject: ...
