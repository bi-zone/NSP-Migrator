from ipaddress import IPv4Address, IPv4Network

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanDeviceObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
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
    AddrObjectResponse,
    AddrObjectType,
    DeviceObjectResponse,
    NetworkResponse,
    ServiceResponse,
    ZoneResponse,
)


class SDWANCatalogGateway(SDWANCatalogGatewayPort):

    def __init__(self, sdwan_http_client: ISDWANCspHttpClient) -> None:
        self.sdwan_http_client = sdwan_http_client

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        """Returns all zones, services and addr_objects (full catalog)"""
        all_zones: list[SdwanZone] = await self.get_zones()
        all_services: list[SdwanService] = await self.get_services()
        all_addr_objs: list[SdwanAddrObject] = await self.get_addr_objects()
        all_networks: list[SdwanNetwork] = await self.get_networks()
        return SdwanFullCatalog(
            zones=all_zones,
            services=all_services,
            addr_objs=all_addr_objs,
            networks=all_networks,
        )

    async def get_zones(self, ids: list[int] | None = None) -> list[SdwanZone]:
        """Return zones by ids, or the full zone list when ids is None.

        An explicitly empty list means that caller has no required ids and should
        receive an empty result instead of accidentally loading the full catalog.
        """
        if ids == []:
            return []

        zones: list[ZoneResponse] = await self.sdwan_http_client.get_zones(ids=ids)
        return [
            SdwanZone(
                id=zone.id,
                zone_id=zone.zone_id,
                name=zone.name,
                type=SdwanZoneType(zone.typ),
            )
            for zone in zones
        ]

    async def get_services(self, ids: list[int] | None = None) -> list[SdwanService]:
        """Return services by ids, or the full service list when ids is None."""
        if ids == []:
            return []

        services: list[ServiceResponse] = await self.sdwan_http_client.get_services(
            ids=ids
        )

        services_result: list[SdwanService] = []

        for service in services:

            ranges = None
            codes = None

            if service.ranges is not None:
                ranges = tuple((r.start, r.end) for r in service.ranges)

            if service.codes is not None:
                codes = tuple(str(c) for c in service.codes)

            services_result.append(
                SdwanService(
                    id=service.id,
                    name=service.name,
                    l4_proto=SdwanServiceL4Proto(service.l4_proto),
                    ranges=ranges,
                    codes=codes,
                )
            )

        return services_result

    async def get_addr_objects(
        self, ids: list[int] | None = None
    ) -> list[SdwanAddrObject]:
        """Return address objects by ids with expanded groups and resolved networks.

        Nested address groups are recursively expanded into the returned flat list.
        Network address objects are enriched with IPv4Network values. Passing None
        intentionally loads all address objects; passing [] returns [] to avoid an
        accidental full-catalog request.
        """
        if ids == []:
            return []

        addr_objs: list[SdwanAddrObject] = await self._get_addr_objects_from_resp(
            addr_objs_responses=(
                await self._get_addr_objects_resp_with_expanded_groups(initial_ids=ids)
            )
        )
        return addr_objs

    async def get_networks(self, ids: list[str] | None = None) -> list[SdwanNetwork]:
        """Return networks by ids, or the full network list when ids is None."""
        if ids == []:
            return []

        networks: list[NetworkResponse] = await self.sdwan_http_client.get_networks(
            network_ids=ids
        )

        networks_result: list[SdwanNetwork] = []

        for netw in networks:
            # skip (invalid?) networks without net
            if netw.net is None:
                continue

            networks_result.append(
                SdwanNetwork(
                    network_id=netw.network_id,
                    net=IPv4Network(netw.net),
                )
            )

        return networks_result

    async def get_sdwan_device_objects(self) -> list[SdwanDeviceObject]:
        device_objects: list[DeviceObjectResponse] = (
            await self.sdwan_http_client.get_device_objects()
        )
        return [
            SdwanDeviceObject(
                dev_obj_id=d.dev_obj_id,
                name=d.name,
                type=SdwanDeviceObjectType(d.type),
                cpe_id=d.cpe.cpe_id if d.cpe else None,
            )
            for d in device_objects
        ]

    async def get_sdwan_device_object(self, dev_obj_id: str) -> SdwanDeviceObject:
        device_objects: list[DeviceObjectResponse] = (
            await self.sdwan_http_client.get_device_objects(
                dev_obj_id=dev_obj_id,
            )
        )
        if not device_objects:
            raise ValueError(f"No found device object {dev_obj_id}")

        device_obj: DeviceObjectResponse = device_objects[0]

        return SdwanDeviceObject(
            dev_obj_id=device_obj.dev_obj_id,
            name=device_obj.name,
            type=SdwanDeviceObjectType(device_obj.type),
            cpe_id=device_obj.cpe.cpe_id if device_obj.cpe else None,
        )

    async def _get_addr_objects_resp_with_expanded_groups(
        self,
        initial_ids: list[int] | None = None,  # Returns ALL if not provided
        max_groups_depth: int = 3,
    ) -> list[AddrObjectResponse]:
        """Return address objects with recursively expanded address groups.

        Example:
            Initial objects:
                [group 1, object 1]

            group 1 children:
                [group 2, object 1]

            Result:
                [group 1, object 1, group 2, object 1]

        Objects are deduplicated by `(id, parents)`, not only by `id`.
        This preserves the same object if it belongs to different parent groups.

        Callers should additionally deduplicate by `id` if they need unique objects only.
        """

        loaded_by_key: dict[tuple[int, tuple[int, ...]], AddrObjectResponse] = {}

        def _addr_object_nesting_key(
            addr_obj: AddrObjectResponse,
        ) -> tuple[int, tuple[int, ...]]:
            """Return a key that preserves the same object under different parents."""
            return int(addr_obj.id), tuple(sorted(addr_obj.parents))

        def _save_objects_and_return_groups_ids(
            addr_objects: list[AddrObjectResponse],
        ) -> list[int]:
            group_ids: list[int] = []

            for addr_obj in addr_objects:
                loaded_by_key[_addr_object_nesting_key(addr_obj)] = addr_obj

                if addr_obj.data.type == AddrObjectType.ADDR_GROUP:
                    group_ids.append(addr_obj.id)

            return group_ids

        initial_objects = await self.sdwan_http_client.get_addr_objects(
            ids=initial_ids,
        )

        current_group_ids: list[int] = _save_objects_and_return_groups_ids(
            initial_objects
        )

        for depth in range(1, max_groups_depth + 1):
            if not current_group_ids:
                break

            children = await self.sdwan_http_client.get_addr_objects_by_parents_ids(
                parents_ids=current_group_ids,
            )

            child_group_ids: list[int] = _save_objects_and_return_groups_ids(children)

            if depth == max_groups_depth and child_group_ids:
                raise ValueError(
                    f"Address group nesting depth exceeded. "
                    f"Max depth is {max_groups_depth}. "
                    f"Nested groups found: {child_group_ids}"
                )

            current_group_ids = child_group_ids

        return list(loaded_by_key.values())

    async def _get_addr_objects_from_resp(  # noqa: C901
        self,
        addr_objs_responses: list[AddrObjectResponse],
    ) -> list[SdwanAddrObject]:
        """Enrich network address objects with resolved NetworkResponse.

        Address object типа network хранит только ссылку:
            {"type": "network", "network": "network_id-..."}

        Для value comparison нам нужен сам IPv4 prefix из network.net.
        Поэтому мы догружаем networks
        """

        # -- get and resolve networks objects
        network_ids: set[str] = {
            ao.data.network
            for ao in addr_objs_responses
            if ao.data.type == AddrObjectType.NETWORK
        }

        networks_by_id: dict[str, SdwanNetwork] = {}
        if network_ids:
            networks: list[SdwanNetwork] = await self.get_networks(
                ids=list(network_ids),
            )
            networks_by_id = {network.network_id: network for network in networks}

        # -- convert to common sdwan addr objects
        addr_objects: list[SdwanAddrObject] = []

        for ao_resp in addr_objs_responses:

            match ao_resp.data.type:
                case AddrObjectType.HOST:
                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.HOST,
                            host=IPv4Address(ao_resp.data.host),
                        )
                    )

                case AddrObjectType.PREFIX:
                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.PREFIX,
                            prefix=IPv4Network(ao_resp.data.prefix),
                        )
                    )

                case AddrObjectType.FQDN:
                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.FQDN,
                            fqdn=ao_resp.data.fqdn,
                        )
                    )

                case AddrObjectType.IP_RANGE:
                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.IP_RANGE,
                            ip_range_from=IPv4Address(ao_resp.data.from_),
                            ip_range_to=IPv4Address(ao_resp.data.to),
                        )
                    )

                case AddrObjectType.NETWORK:
                    network: SdwanNetwork | None = networks_by_id.get(
                        ao_resp.data.network, None
                    )
                    if (
                        not network
                    ):  # Network has no net (filtered in get_networks method)
                        continue

                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.NETWORK,
                            network_id=network.network_id,
                            network=network.net,
                        )
                    )

                case AddrObjectType.ADDR_GROUP:
                    addr_objects.append(
                        SdwanAddrObject(
                            id=ao_resp.id,
                            parents=tuple(ao_resp.parents),
                            name=ao_resp.name,
                            type=SdwanAddrObjectType.ADDR_GROUP,
                            addr_group=ao_resp.data.addr_group,
                        )
                    )

                case _:
                    raise ValueError(
                        f"Unsupported addr object data type: {ao_resp.data.type}"
                    )

        return addr_objects
