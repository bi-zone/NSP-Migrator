from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse


class ReportsSDWANGatewayPort(ABC):
    """SD-WAN data required to build one immutable report snapshot."""

    @abstractmethod
    async def get_target(self, target_id: str) -> SdwanDeviceObject | None: ...

    @abstractmethod
    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog: ...


class ReportsSDWANGatewayProviderPort(Protocol):
    """Create profile/VPC-scoped SD-WAN gateways for report persistence."""

    @abstractmethod
    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]: ...

    @abstractmethod
    def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AbstractAsyncContextManager[ReportsSDWANGatewayPort]: ...
