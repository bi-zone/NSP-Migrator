from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanDeviceObject,
    SdwanFullCatalog,
    SdwanNetwork,
    SdwanService,
    SdwanZone,
)
from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.integrations.sdwan_csp_api.schemas import (
    CreateAddrObjectFqdnRequestData,
    CreateAddrObjectHostRequestData,
    CreateAddrObjectIpRangeRequestData,
    CreateAddrObjectPrefixRequestData,
    CreateAddrObjectRequest,
    CreateAddrObjectRequestData,
    ServiceCreateRequest,
    ServiceL4Proto,
    ServicePortRange,
    ServiceResponse,
)
from app.modules.mapping.ports.gateways import (
    CreateAddrObjectPayload,
    CreateServicePayload,
    MappingSDWANGatewayPort,
)


class MappingSDWANGateway(MappingSDWANGatewayPort):
    """Здесь реализованы именно методы, привязанные к доменной логике mapping модуля,
    методы ближе к API SD-WAN реализованы в ISDWANCspHttpClient
    """

    def __init__(
        self,
        sdwan_http_client: ISDWANCspHttpClient,
        catalog_gateway: SDWANCatalogGatewayPort,
    ) -> None:
        self.sdwan_http_client = sdwan_http_client
        self.catalog_gateway = catalog_gateway

    async def health_check(self) -> None:
        await self.sdwan_http_client.health_check()

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        """Returns all zones, services and addr_objects (full catalog)"""
        return await self.catalog_gateway.get_sdwan_full_catalog()

    async def get_zones(self) -> list[SdwanZone]:
        return await self.catalog_gateway.get_zones()

    async def get_services(self) -> list[SdwanService]:
        return await self.catalog_gateway.get_services()

    async def get_addr_objects(self) -> list[SdwanAddrObject]:
        return await self.catalog_gateway.get_addr_objects()

    async def get_networks(self) -> list[SdwanNetwork]:
        return await self.catalog_gateway.get_networks()

    async def get_zone(self, zone_id: int) -> SdwanZone | None:
        response: list[SdwanZone] = await self.catalog_gateway.get_zones(ids=[zone_id])
        if len(response) == 0:
            return None

        return response[0]

    async def get_service(self, service_id: int) -> SdwanService | None:
        response: list[SdwanService] = await self.catalog_gateway.get_services(
            ids=[service_id]
        )
        if len(response) == 0:
            return None

        return response[0]

    async def get_addr_object(self, addr_obj_id: int) -> SdwanAddrObject | None:
        response: list[SdwanAddrObject] = await self.catalog_gateway.get_addr_objects(
            ids=[addr_obj_id]
        )
        if len(response) == 0:
            return None

        return response[0]

    async def create_addr_objects_bulk(
        self, payloads: list[CreateAddrObjectPayload]
    ) -> list[int]:
        """Create addr objs"""
        request_datas: list[CreateAddrObjectRequestData] = []
        for payload in payloads:
            match payload.type:
                case SdwanAddrObjectType.PREFIX:
                    if payload.prefix is None:
                        raise ValueError("prefix must be provided for prefix type")
                    request_datas.append(
                        CreateAddrObjectPrefixRequestData(prefix=payload.prefix)
                    )

                case SdwanAddrObjectType.HOST:
                    if payload.host is None:
                        raise ValueError("host must be provided for host type")
                    request_datas.append(
                        CreateAddrObjectHostRequestData(host=payload.host)
                    )

                case SdwanAddrObjectType.FQDN:
                    if payload.fqdn is None:
                        raise ValueError("fqdn must be provided for fqdn type")
                    request_datas.append(
                        CreateAddrObjectFqdnRequestData(fqdn=payload.fqdn)
                    )

                case SdwanAddrObjectType.IP_RANGE:
                    if payload.ip_range_from is None or payload.ip_range_to is None:
                        raise ValueError(
                            "ip_range_from and ip_range_to must be provided for ip_range type"
                        )
                    request_datas.append(
                        CreateAddrObjectIpRangeRequestData(
                            from_=payload.ip_range_from,
                            to=payload.ip_range_to,
                        )
                    )

                case _:
                    raise ValueError("Unexpected addr obj type")

        ids: list[int] = await self.sdwan_http_client.create_addr_objects(
            payloads=[CreateAddrObjectRequest(data=d) for d in request_datas]
        )
        return ids

    async def create_addr_object(
        self, payload: CreateAddrObjectPayload
    ) -> SdwanAddrObject:
        """Create addr obj and return it"""
        created_addr_obj_id: int = (await self.create_addr_objects_bulk([payload]))[0]
        created_addr_obj: SdwanAddrObject | None = await self.get_addr_object(
            created_addr_obj_id
        )
        if not created_addr_obj:
            raise ValueError(f"Addr object {created_addr_obj_id} not found")

        return created_addr_obj

    async def create_service(self, payload: CreateServicePayload) -> SdwanService:
        """Create service and return it"""
        if payload.l4_proto == SdwanServiceL4Proto.ICMP:
            request_payload = ServiceCreateRequest(
                name=payload.name,
                l4_proto=ServiceL4Proto(payload.l4_proto),
                codes=payload.icmp_codes,
            )

        elif payload.l4_proto in (SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP):
            request_payload = ServiceCreateRequest(
                name=payload.name,
                l4_proto=ServiceL4Proto(payload.l4_proto),
                ranges=[
                    ServicePortRange(start=payload.port_start, end=payload.port_end)
                ],
            )

        else:
            raise ValueError(
                f"Unexpected l4_proto {payload.l4_proto} type for auto-creation"
            )

        created_service: ServiceResponse = await self.sdwan_http_client.create_service(
            payload=request_payload
        )

        return SdwanService(
            id=created_service.id,
            name=created_service.name,
            l4_proto=SdwanServiceL4Proto(created_service.l4_proto),
            ranges=(
                tuple((r.start, r.end) for r in created_service.ranges)
                if created_service.ranges
                else None
            ),
            codes=created_service.codes,  # type: ignore
        )

    async def get_device_objects(self) -> list[SdwanDeviceObject]:
        return await self.catalog_gateway.get_sdwan_device_objects()

    async def get_device_object(self, dev_obj_id: str) -> SdwanDeviceObject:
        return await self.catalog_gateway.get_sdwan_device_object(dev_obj_id)
