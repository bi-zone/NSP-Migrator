from dataclasses import dataclass, field
from ipaddress import IPv4Address

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import SdwanAddrObject
from app.integrations.sdwan_csp_api.schemas import (
    CreateAddrObjectRequest,
    ServiceCreateRequest,
    ServiceResponse,
)
from app.modules.mapping.adapters.sdwan_gateway import MappingSDWANGateway
from app.modules.mapping.domain.value_objects import (
    CreateAddrObjectPayload,
    CreateServicePayload,
)


@dataclass
class _HttpClientFake:
    address_requests: list[CreateAddrObjectRequest] = field(default_factory=list)
    service_requests: list[ServiceCreateRequest] = field(default_factory=list)

    async def create_addr_objects(
        self, *, payloads: list[CreateAddrObjectRequest]
    ) -> list[int]:
        self.address_requests.extend(payloads)
        return list(range(100, 100 + len(payloads)))

    async def create_service(self, *, payload: ServiceCreateRequest) -> ServiceResponse:
        self.service_requests.append(payload)
        return ServiceResponse(
            id=200,
            name=payload.name,
            l4_proto=payload.l4_proto,
            ranges=payload.ranges,
            codes=payload.codes,
        )


@dataclass
class _CatalogGatewayFake:
    address_objects: list[SdwanAddrObject] = field(default_factory=list)

    async def get_addr_objects(self, *, ids: list[int]) -> list[SdwanAddrObject]:
        return [item for item in self.address_objects if item.id in ids]


@pytest.mark.asyncio
async def test_mapping_gateway_translates_all_supported_address_creation_payloads() -> (
    None
):
    http_client = _HttpClientFake()
    gateway = MappingSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayFake(),  # type: ignore[arg-type]
    )

    created_ids = await gateway.create_addr_objects_bulk(
        [
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.PREFIX,
                prefix="192.0.2.0/24",
            ),
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.HOST,
                host="192.0.2.10",
            ),
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.FQDN,
                fqdn="example.test",
            ),
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.IP_RANGE,
                ip_range_from="192.0.2.20",
                ip_range_to="192.0.2.30",
            ),
        ]
    )

    assert created_ids == [100, 101, 102, 103]
    assert [
        request.data.model_dump(by_alias=True)
        for request in http_client.address_requests
    ] == [
        {"type": "prefix", "prefix": "192.0.2.0/24", "raw": False},
        {"type": "host", "host": "192.0.2.10", "raw": False},
        {"type": "fqdn", "fqdn": "example.test", "raw": False},
        {
            "type": "ip_range",
            "from": "192.0.2.20",
            "to": "192.0.2.30",
            "raw": False,
        },
    ]


@pytest.mark.asyncio
async def test_mapping_gateway_loads_created_address_and_maps_service_response() -> (
    None
):
    created_address = SdwanAddrObject(
        id=100,
        parents=(),
        name="created-host",
        type=SdwanAddrObjectType.HOST,
        host=IPv4Address("192.0.2.10"),
    )
    http_client = _HttpClientFake()
    gateway = MappingSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayFake([created_address]),  # type: ignore[arg-type]
    )

    address = await gateway.create_addr_object(
        CreateAddrObjectPayload(
            type=SdwanAddrObjectType.HOST,
            host="192.0.2.10",
        )
    )
    service = await gateway.create_service(
        CreateServicePayload(
            name="https",
            l4_proto=SdwanServiceL4Proto.TCP,
            port_start=443,
            port_end=443,
        )
    )

    assert address == created_address
    assert http_client.service_requests[0].model_dump() == {
        "name": "https",
        "description": None,
        "l4_proto": "tcp",
        "ranges": [{"start": 443, "end": 443}],
        "codes": None,
    }
    assert service.id == 200
    assert service.l4_proto == SdwanServiceL4Proto.TCP
    assert service.ranges == ((443, 443),)
