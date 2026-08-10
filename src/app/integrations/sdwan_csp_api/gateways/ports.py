from abc import ABC, abstractmethod

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanDeviceObject,
    SdwanFullCatalog,
    SdwanNetwork,
    SdwanService,
    SdwanZone,
)


class SDWANCatalogGatewayPort(ABC):

    @abstractmethod
    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        """Returns all zones, services and addr_objects (full catalog)"""
        ...

    @abstractmethod
    async def get_zones(self, ids: list[int] | None = None) -> list[SdwanZone]: ...

    @abstractmethod
    async def get_services(
        self, ids: list[int] | None = None
    ) -> list[SdwanService]: ...

    @abstractmethod
    async def get_addr_objects(
        self, ids: list[int] | None = None
    ) -> list[SdwanAddrObject]: ...

    @abstractmethod
    async def get_networks(
        self, ids: list[str] | None = None
    ) -> list[SdwanNetwork]: ...

    @abstractmethod
    async def get_sdwan_device_objects(self) -> list[SdwanDeviceObject]: ...

    @abstractmethod
    async def get_sdwan_device_object(self, dev_obj_id: str) -> SdwanDeviceObject: ...
