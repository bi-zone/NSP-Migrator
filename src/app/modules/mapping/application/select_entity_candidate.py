from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.mapping.domain.entities import (
    MappingEntityCandidate,
    MappingEntityResult,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class SelectEntityCandidateCommand:

    mapping_entity_result_id: UUID
    candidate_id: UUID


@dataclass(frozen=True, slots=True)
class SelectEntityCandidateResult:

    mapping_entity_result: MappingEntityResult


class SelectEntityCandidateUseCase:
    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
    ) -> None:
        self.uow = uow

    @async_transactional(read_only=False)
    async def execute(
        self,
        command: SelectEntityCandidateCommand,
    ) -> SelectEntityCandidateResult:

        mapping_result: MappingEntityResult | None = (
            await self.uow.mapping_result_repo.get_result_by_id(
                result_id=command.mapping_entity_result_id,
                with_candidates=True,
            )
        )
        if not mapping_result:
            raise MappingModuleNotFoundError(
                f"Mapping Result with id {command.mapping_entity_result_id} not found"
            )

        if not mapping_result.candidates:
            raise MappingModuleDomainValidationError("Candidates not provided")

        if len(mapping_result.candidates) == 0:
            raise MappingModuleDomainValidationError(
                f"Mapping Result with id {command.mapping_entity_result_id} has no candidates"
            )
        elif len(mapping_result.candidates) == 1:
            raise MappingModuleDomainValidationError(
                f"Mapping Result with id {command.mapping_entity_result_id} has single candidate only"
            )

        candidates_by_id: dict[UUID, MappingEntityCandidate] = {
            c.id: c for c in mapping_result.candidates
        }
        selected_candidate: MappingEntityCandidate | None = candidates_by_id.get(
            command.candidate_id, None
        )
        if not selected_candidate:
            raise MappingModuleDomainValidationError(
                f"Candidate {command.candidate_id} not linked to "
                f"MappingResult {command.mapping_entity_result_id}"
            )

        updated_mapping_result: MappingEntityResult = mapping_result.select_candidate(
            candidate=selected_candidate
        )
        await self.uow.mapping_result_repo.save_result(updated_mapping_result)

        return SelectEntityCandidateResult(mapping_entity_result=updated_mapping_result)
