from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import SdwanDeviceObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.reports.adapters.sdwan_gateway import (
    ReportsSDWANGateway,
    ReportsSDWANGatewayProvider,
)


class _CatalogGateway:
    def __init__(
        self,
        *,
        target: SdwanDeviceObject | None,
        catalog: SdwanFullCatalog,
    ) -> None:
        self.target = target
        self.catalog = catalog
        self.requested_target_id: str | None = None

    async def get_sdwan_device_object(
        self, dev_obj_id: str
    ) -> SdwanDeviceObject | None:
        self.requested_target_id = dev_obj_id
        return self.target

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return self.catalog


class _ClientProvider:
    def __init__(self, vpcs: list[AllowedVPCResponse]) -> None:
        self.vpcs = vpcs
        self.discovered_profile_id = None
        self.acquired: list[tuple[object, str]] = []

    async def discover_vpcs(self, profile_id):
        self.discovered_profile_id = profile_id
        return self.vpcs

    @asynccontextmanager
    async def acquire(self, profile_id, vpc_id: str) -> AsyncIterator[object]:
        self.acquired.append((profile_id, vpc_id))
        yield object()


def _catalog() -> SdwanFullCatalog:
    return SdwanFullCatalog(zones=[], services=[], addr_objs=[], networks=[])


@pytest.mark.asyncio
async def test_reports_gateway_delegates_target_and_catalog_reads() -> None:
    target = SdwanDeviceObject(
        dev_obj_id="target-1",
        name="Branch gateway",
        type=SdwanDeviceObjectType.DEVICE,
        cpe_id="cpe-1",
    )
    catalog_gateway = _CatalogGateway(target=target, catalog=_catalog())
    gateway = ReportsSDWANGateway(catalog_gateway)  # type: ignore[arg-type]

    assert await gateway.get_target("target-1") == target
    assert catalog_gateway.requested_target_id == "target-1"
    assert await gateway.get_sdwan_full_catalog() == _catalog()


@pytest.mark.asyncio
async def test_reports_gateway_provider_uses_client_context() -> None:
    profile_id = uuid4()
    client_provider = _ClientProvider(
        [
            AllowedVPCResponse(
                vpc_id="vpc-1",
                customer_name="Customer",
                project_name="Project",
                cuid="cuid-1",
                pid="pid-1",
            )
        ]
    )
    provider = ReportsSDWANGatewayProvider(client_provider)  # type: ignore[arg-type]

    assert await provider.discover_vpcs(profile_id) == client_provider.vpcs
    assert client_provider.discovered_profile_id == profile_id

    async with provider.acquire(profile_id, "vpc-1") as gateway:
        assert isinstance(gateway, ReportsSDWANGateway)

    assert client_provider.acquired == [(profile_id, "vpc-1")]
