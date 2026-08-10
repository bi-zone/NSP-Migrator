from collections import defaultdict
from ipaddress import IPv4Address, IPv4Network

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
)
from app.modules.mapping.domain.exceptions import MappingModuleDomainValidationError
from app.modules.mapping.services.mapping_objects.normalizer import (
    deduplicate_objects_by_id,
    normalize_fqdn,
    normalize_name,
)


class SdwanAddrObjsCatalogIndex:
    """
    Readable in-memory lookup facade over SD-WAN catalog of address objects
    that is used for objects mapping by fields indexes.
    """

    def __init__(self, addr_objs: list[SdwanAddrObject]) -> None:
        self._addr_objects = deduplicate_objects_by_id(addr_objs)

        self._addr_by_name: dict[str, list[SdwanAddrObject]] = defaultdict(list)
        self._addr_by_host: dict[str, list[SdwanAddrObject]] = defaultdict(list)
        self._addr_by_prefix: dict[str, list[SdwanAddrObject]] = defaultdict(list)
        self._addr_by_fqdn: dict[str, list[SdwanAddrObject]] = defaultdict(list)
        self._addr_by_range: dict[
            tuple[str, str],
            list[SdwanAddrObject],
        ] = defaultdict(list)

        self._build_indexes()

    def find_addr_by_name(self, name: str) -> list[SdwanAddrObject]:
        return self._addr_by_name.get(normalize_name(name), [])

    def find_addr_by_host(self, host: str | IPv4Address) -> list[SdwanAddrObject]:
        return self._addr_by_host.get(str(IPv4Address(host)), [])

    def find_addr_by_prefix(
        self,
        prefix: str | IPv4Network,
    ) -> list[SdwanAddrObject]:
        return self._addr_by_prefix.get(str(IPv4Network(prefix, strict=False)), [])

    def find_addr_by_fqdn(self, fqdn: str) -> list[SdwanAddrObject]:
        return self._addr_by_fqdn.get(normalize_fqdn(fqdn), [])

    def find_addr_by_range(
        self,
        range_start: str | IPv4Address,
        range_end: str | IPv4Address,
    ) -> list[SdwanAddrObject]:
        key = (str(IPv4Address(range_start)), str(IPv4Address(range_end)))
        return self._addr_by_range.get(key, [])

    def find_builtin_any_addr_objects(self) -> list[SdwanAddrObject]:
        """
        Return SD-WAN objects that can represent ANY address.

        Current heuristic:
        - prefix/network 0.0.0.0/0;
        - normalized name equals any/all.
        """
        result: list[SdwanAddrObject] = []
        seen: set[int] = set()

        for item in self.find_addr_by_prefix("0.0.0.0/0"):
            if item.id not in seen:
                seen.add(item.id)
                result.append(item)

        for name in ("any", "all"):
            for item in self.find_addr_by_name(name):
                if item.id not in seen:
                    seen.add(item.id)
                    result.append(item)

        return result

    def _build_indexes(self) -> None:

        for addr in self._addr_objects:

            self._addr_by_name[normalize_name(addr.name)].append(addr)

            if addr.type == SdwanAddrObjectType.HOST and addr.host is not None:
                self._addr_by_host[str(addr.host)].append(addr)

            elif addr.type == SdwanAddrObjectType.PREFIX and addr.prefix is not None:
                self._addr_by_prefix[str(addr.prefix)].append(addr)

            elif addr.type == SdwanAddrObjectType.NETWORK and addr.network is not None:
                self._addr_by_prefix[str(addr.network)].append(addr)

            elif addr.type == SdwanAddrObjectType.FQDN and addr.fqdn is not None:
                self._addr_by_fqdn[normalize_fqdn(addr.fqdn)].append(addr)

            elif (
                addr.type == SdwanAddrObjectType.IP_RANGE
                and addr.ip_range_from is not None
                and addr.ip_range_to is not None
            ):
                self._addr_by_range[
                    (str(addr.ip_range_from), str(addr.ip_range_to))
                ].append(addr)

            elif addr.type == SdwanAddrObjectType.ADDR_GROUP:
                # Ignore addr groups through indexes building
                continue

            else:
                raise MappingModuleDomainValidationError(
                    f"Unexpected for index addr obj type `{addr.type}`"
                )
