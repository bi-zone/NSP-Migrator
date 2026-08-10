from collections import defaultdict

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanZone,
)
from app.modules.mapping.services.mapping_objects.normalizer import (
    deduplicate_objects_by_id,
    normalize_name,
)


class SdwanZonesCatalogIndex:
    """
    Readable in-memory lookup facade over SD-WAN catalog of zones
    that is used for objects mapping by fields indexes.
    """

    def __init__(self, zones: list[SdwanZone]) -> None:
        self._zones = deduplicate_objects_by_id(zones)

        self._zones_by_name: dict[str, list[SdwanZone]] = defaultdict(list)

        self._build_indexes()

    def find_zones_by_name(self, name: str) -> list[SdwanZone]:
        return list(self._zones_by_name.get(normalize_name(name), []))

    def _build_indexes(self) -> None:
        for zone in self._zones:
            self._zones_by_name[normalize_name(zone.name)].append(zone)
