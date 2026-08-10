from uuid import UUID

from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import CanonicalZone


class CanonicalZoneIndex:
    def __init__(self, zones: list[CanonicalZone]) -> None:
        self._zones_by_id: dict[UUID, CanonicalZone] = {}

        for zone in zones:
            if zone.id in self._zones_by_id:
                raise MappingModuleDomainValidationError(
                    f"Duplicate canonical zone id: {zone.id}"
                )

            self._zones_by_id[zone.id] = zone

    def get(self, zone_id: UUID) -> CanonicalZone:
        zone = self._zones_by_id.get(zone_id)

        if zone is None:
            raise MappingModuleNotFoundError(f"Canonical zone not found: {zone_id}")

        return zone
