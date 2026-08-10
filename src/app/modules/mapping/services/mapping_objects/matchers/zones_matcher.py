from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanZone,
)
from app.modules.mapping.domain.enums import CandidateMatchStrategy
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalZone,
)
from app.modules.mapping.services.mapping_objects.matchers.utils import (
    CandidateDraft,
    CandidateFinalizer,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.zones_catalog_index import (
    SdwanZonesCatalogIndex,
)

_ZONE_BY_NAME_SCORE = 90


class ZoneMatcher:
    """
    Matches canonical zones to SD-WAN zones.

    Strategies:
    - normalized canonical name equals normalized SD-WAN name.
    """

    def __init__(self, catalog_index: SdwanZonesCatalogIndex) -> None:
        self._catalog_index = catalog_index

    def match(self, zone: CanonicalZone) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        for sdwan_zone in self._catalog_index.find_zones_by_name(zone.name):
            candidates.append(
                self._candidate(
                    sdwan_zone,
                    _ZONE_BY_NAME_SCORE,
                    CandidateMatchStrategy.NORMALIZED_NAME,
                )
            )

        return CandidateFinalizer.finalize(candidates)

    @staticmethod
    def _candidate(
        zone: SdwanZone,
        score: int,
        strategy: CandidateMatchStrategy,
    ) -> CandidateDraft:
        return CandidateDraft(
            sdwan_entity_id=zone.id,
            score=score,
            strategy=strategy,
        )
