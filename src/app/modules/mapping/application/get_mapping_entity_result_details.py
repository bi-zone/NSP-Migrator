from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.mapping.application.dto import (
    MappedSdwanEntityDisplayDTO,
    MappingEntityCandidateDisplayDTO,
    MappingEntityResultDetailsDTO,
)
from app.modules.mapping.domain.entities import (
    MappingEntityCandidate,
    MappingEntityResult,
)
from app.modules.mapping.domain.enums import MappingResultStatus
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort
from app.modules.mapping.services.mapping_rules.sdwan_full_catalog_index import (
    SdwanEntityDTO,
    SdwanFullCatalogIndex,
)


@dataclass(frozen=True, slots=True)
class GetMappingEntityResultDetailsQuery:
    mapping_result_id: UUID


@dataclass(frozen=True, slots=True)
class GetMappingEntityResultDetailsResult:
    details: MappingEntityResultDetailsDTO


class GetMappingEntityResultDetailsUseCase:
    """Load one mapping result with candidates and SD-WAN display data for UI editors."""

    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
        sdwan_gateway: MappingSDWANGatewayPort,
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GetMappingEntityResultDetailsQuery,
    ) -> GetMappingEntityResultDetailsResult:
        mapping_result: MappingEntityResult | None = (
            await self.uow.mapping_result_repo.get_result_by_id(
                result_id=query.mapping_result_id,
                with_candidates=True,
            )
        )
        if mapping_result is None:
            raise MappingModuleNotFoundError(
                f"Mapping result {query.mapping_result_id} not found"
            )

        catalog: SdwanFullCatalog = await self.sdwan_gateway.get_sdwan_full_catalog()
        sdwan_index = SdwanFullCatalogIndex(catalog)

        return GetMappingEntityResultDetailsResult(
            details=MappingEntityResultDetailsDTO(
                mapping_result_id=mapping_result.id,
                mapping_scope_id=mapping_result.mapping_scope_id,
                entity_type=mapping_result.entity_type,
                canonical_entity_id=self._canonical_entity_id_or_none(mapping_result),
                match_status=mapping_result.result_status,
                selection_method=mapping_result.selection_method,
                selected_sdwan=self._selected_sdwan_display(
                    mapping_result=mapping_result,
                    sdwan_index=sdwan_index,
                ),
                candidates=self._candidate_displays(
                    mapping_result=mapping_result,
                    sdwan_index=sdwan_index,
                ),
            )
        )

    @staticmethod
    def _canonical_entity_id_or_none(
        mapping_result: MappingEntityResult,
    ) -> UUID | None:
        try:
            return mapping_result.canonical_entity_id
        except ValueError:
            return None

    @staticmethod
    def _selected_sdwan_display(
        *,
        mapping_result: MappingEntityResult,
        sdwan_index: SdwanFullCatalogIndex,
    ) -> MappedSdwanEntityDisplayDTO | None:
        if mapping_result.result_status != MappingResultStatus.MATCHED:
            return None

        if mapping_result.selected_sdwan_entity_id is None:
            raise MappingModuleDomainValidationError(
                "Matched mapping result must have selected SD-WAN entity id: "
                f"{mapping_result.id}"
            )

        display: SdwanEntityDTO = sdwan_index.get_display_entity(
            entity_type=mapping_result.entity_type,
            sdwan_entity_id=mapping_result.selected_sdwan_entity_id,
        )
        return MappedSdwanEntityDisplayDTO(
            mapping_result_id=mapping_result.id,
            match_status=mapping_result.result_status,
            selection_method=mapping_result.selection_method,
            sdwan_id=display.sdwan_id,
            name=display.name,
            type=display.type,
            str_value=display.str_value,
        )

    @classmethod
    def _candidate_displays(
        cls,
        *,
        mapping_result: MappingEntityResult,
        sdwan_index: SdwanFullCatalogIndex,
    ) -> list[MappingEntityCandidateDisplayDTO]:
        candidates: list[MappingEntityCandidate] = list(mapping_result.candidates or [])
        return [
            cls._candidate_display(
                mapping_result=mapping_result,
                candidate=candidate,
                sdwan_index=sdwan_index,
            )
            for candidate in sorted(
                candidates, key=lambda item: (item.rank, -item.score)
            )
        ]

    @staticmethod
    def _candidate_display(
        *,
        mapping_result: MappingEntityResult,
        candidate: MappingEntityCandidate,
        sdwan_index: SdwanFullCatalogIndex,
    ) -> MappingEntityCandidateDisplayDTO:
        display: SdwanEntityDTO = sdwan_index.get_display_entity(
            entity_type=mapping_result.entity_type,
            sdwan_entity_id=candidate.sdwan_entity_id,
        )
        return MappingEntityCandidateDisplayDTO(
            candidate_id=candidate.id,
            rank=candidate.rank,
            score=candidate.score,
            strategy=candidate.strategy,
            sdwan_id=candidate.sdwan_entity_id,
            name=display.name,
            type=display.type,
            str_value=display.str_value,
        )
