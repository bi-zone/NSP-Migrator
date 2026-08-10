from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.entities import MappingEntityResult
from app.modules.mapping.domain.enums import MappingEntityType


@dataclass(frozen=True, slots=True)
class MappingResultLookupKey:
    """
    Lookup key for mapping entity result.
    """

    entity_type: MappingEntityType
    canonical_entity_id: UUID


class MappingResultsIndex:
    """
    In-memory index over MappingEntityResult rows.

    Used by MappingScopeRulesBuilder to resolve canonical operands into selected
    SD-WAN ids.
    """

    def __init__(self, results: list[MappingEntityResult]) -> None:
        self._by_key: dict[MappingResultLookupKey, MappingEntityResult] = {}

        for result in results:

            try:
                canonical_entity_id: UUID = result.canonical_entity_id
            except ValueError as e:
                # ignore empty canonical id for zones, that can be assigned manually
                if result.entity_type == MappingEntityType.ZONE:
                    continue
                raise e

            key = MappingResultLookupKey(
                entity_type=result.entity_type,
                canonical_entity_id=canonical_entity_id,
            )
            self._by_key[key] = result

    def get(
        self,
        *,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
    ) -> MappingEntityResult | None:
        return self._by_key.get(
            MappingResultLookupKey(
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
            )
        )
