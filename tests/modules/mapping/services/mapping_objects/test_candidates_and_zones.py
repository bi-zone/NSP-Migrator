from uuid import uuid4

from app.integrations.sdwan_csp_api.gateways.enums import SdwanZoneType
from app.integrations.sdwan_csp_api.gateways.models import SdwanZone
from app.modules.mapping.domain.enums import CandidateMatchStrategy
from app.modules.mapping.ports.canonical_reader.schemas import CanonicalZone
from app.modules.mapping.services.mapping_objects.matchers.utils import (
    CandidateDraft,
    CandidateFinalizer,
)
from app.modules.mapping.services.mapping_objects.matchers.zones_matcher import (
    ZoneMatcher,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.zones_catalog_index import (
    SdwanZonesCatalogIndex,
)


def test_candidate_finalizer_keeps_best_candidate_and_stable_rank_order() -> None:
    candidates = CandidateFinalizer.finalize(
        [
            CandidateDraft(
                sdwan_entity_id=20,
                score=90,
                strategy=CandidateMatchStrategy.NORMALIZED_NAME,
            ),
            CandidateDraft(
                sdwan_entity_id=10,
                score=100,
                strategy=CandidateMatchStrategy.EXACT_VALUE,
            ),
            CandidateDraft(
                sdwan_entity_id=20,
                score=100,
                strategy=CandidateMatchStrategy.BUILTIN_ANY,
            ),
            CandidateDraft(
                sdwan_entity_id=30,
                score=100,
                strategy=CandidateMatchStrategy.SERVICE_SIGNATURE,
            ),
        ]
    )

    assert [
        (candidate.rank, candidate.sdwan_entity_id, candidate.strategy)
        for candidate in candidates
    ] == [
        (1, 10, CandidateMatchStrategy.EXACT_VALUE),
        (2, 20, CandidateMatchStrategy.BUILTIN_ANY),
        (3, 30, CandidateMatchStrategy.SERVICE_SIGNATURE),
    ]


def test_zones_catalog_index_normalizes_names_and_removes_duplicate_ids() -> None:
    duplicate = SdwanZone(
        id=1,
        zone_id=101,
        name="Old LAN",
        type=SdwanZoneType.LAN,
    )
    expected = SdwanZone(
        id=1,
        zone_id=101,
        name="Branch_LAN",
        type=SdwanZoneType.LAN,
    )
    index = SdwanZonesCatalogIndex(
        [
            expected,
            duplicate,
            SdwanZone(
                id=2,
                zone_id=102,
                name="DMZ West",
                type=SdwanZoneType.WAN,
            ),
        ]
    )

    assert index.find_zones_by_name(" branch-lan ") == [expected]
    assert index.find_zones_by_name("dmz_west") == [
        SdwanZone(
            id=2,
            zone_id=102,
            name="DMZ West",
            type=SdwanZoneType.WAN,
        )
    ]
    assert index.find_zones_by_name("missing") == []


def test_zone_matcher_returns_ranked_normalized_name_candidates() -> None:
    matching_zone = SdwanZone(
        id=2,
        zone_id=102,
        name="dmz-west",
        type=SdwanZoneType.WAN,
    )
    matcher = ZoneMatcher(
        SdwanZonesCatalogIndex(
            [
                SdwanZone(
                    id=1,
                    zone_id=101,
                    name="LAN",
                    type=SdwanZoneType.LAN,
                ),
                matching_zone,
            ]
        )
    )

    candidates = matcher.match(
        CanonicalZone(
            id=uuid4(),
            zone_key="dmz-west",
            name="DMZ West",
        )
    )

    assert len(candidates) == 1
    assert candidates[0].rank == 1
    assert candidates[0].score == 90
    assert candidates[0].strategy == CandidateMatchStrategy.NORMALIZED_NAME
    assert candidates[0].sdwan_entity_id == matching_zone.id
