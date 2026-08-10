from dataclasses import dataclass

from app.modules.mapping.domain.enums import CandidateMatchStrategy
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    """
    Internal candidate draft before rank is assigned.

    Matchers may produce duplicate SD-WAN ids by different strategies.
    The finalizer deduplicates them and keeps the best score.
    """

    sdwan_entity_id: int
    score: int
    strategy: CandidateMatchStrategy


class CandidateFinalizer:
    """
    Converts raw matcher candidates into MappingEntityCandidatePayload objects.
    """

    @staticmethod
    def finalize(
        candidates: list[CandidateDraft],
    ) -> list[MappingEntityCandidatePayload]:
        """
        Deduplicate candidates by SD-WAN id and assign stable rank.

        Higher score wins. If the same SD-WAN id is produced several times,
        the best-scored candidate is kept.
        """
        best_by_id: dict[int, CandidateDraft] = {}

        for candidate in candidates:
            current = best_by_id.get(candidate.sdwan_entity_id)

            if current is None or candidate.score > current.score:
                best_by_id[candidate.sdwan_entity_id] = candidate

        sorted_candidates = sorted(
            best_by_id.values(),
            key=lambda item: (-item.score, item.sdwan_entity_id),
        )

        return [
            MappingEntityCandidatePayload(
                rank=index,
                score=candidate.score,
                strategy=candidate.strategy,
                sdwan_entity_id=candidate.sdwan_entity_id,
            )
            for index, candidate in enumerate(sorted_candidates, start=1)
        ]
