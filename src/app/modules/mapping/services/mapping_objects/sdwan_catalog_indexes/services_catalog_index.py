from collections import defaultdict

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanService,
)
from app.modules.mapping.services.mapping_objects.normalizer import (
    deduplicate_objects_by_id,
    normalize_name,
)


class SdwanServicesCatalogIndex:
    """
    Readable in-memory lookup facade over SD-WAN catalog of services
    that is used for objects mapping by fields indexes.
    """

    def __init__(self, services: list[SdwanService]) -> None:
        self._services = deduplicate_objects_by_id(services)

        self._services_by_name: dict[str, list[SdwanService]] = defaultdict(list)
        self._services_by_signature: dict[
            tuple[SdwanServiceL4Proto, tuple[tuple[int, int], ...], tuple[str, ...]],
            list[SdwanService],
        ] = defaultdict(
            list
        )  # [proto, ports | (), codes | ()]

        self._build_indexes()

    def find_services_by_name(self, name: str) -> list[SdwanService]:
        return list(self._services_by_name.get(normalize_name(name), []))

    def find_services_by_signature(
        self,
        *,
        l4_proto: SdwanServiceL4Proto,
        ranges: tuple[tuple[int, int], ...] = (),
        codes: tuple[str, ...] = (),
    ) -> list[SdwanService]:
        key = (
            l4_proto,
            tuple(sorted(ranges)),
            tuple(sorted(codes)),
        )
        return list(self._services_by_signature.get(key, []))

    def find_icmp_services_by_codes(self, codes: tuple[str, ...]) -> list[SdwanService]:
        """
        Find ICMP services by exact code set.

        If SD-WAN stores ICMP differently, this is the only method that should
        be changed, not the service matcher.
        """
        target_codes = tuple(sorted(codes))
        result: list[SdwanService] = []

        for service in self._services:
            if service.l4_proto != SdwanServiceL4Proto.ICMP:
                continue

            service_codes = tuple(sorted(service.codes or ()))
            if service_codes == target_codes:
                result.append(service)

        return result

    def find_builtin_any_services(self) -> list[SdwanService]:
        """
        Return SD-WAN services that can represent ANY service.

        Current heuristic:
        - service name any/all;
        """
        result: list[SdwanService] = []
        seen: set[int] = set()

        for name in ("any", "all"):
            for item in self.find_services_by_name(name):
                if item.id not in seen:
                    seen.add(item.id)
                    result.append(item)

        return result

    def _build_indexes(self) -> None:

        for service in self._services:
            self._services_by_name[normalize_name(service.name)].append(service)

            key = (
                service.l4_proto,
                tuple(sorted(service.ranges or ())),
                tuple(sorted(service.codes or ())),
            )
            self._services_by_signature[key].append(service)
