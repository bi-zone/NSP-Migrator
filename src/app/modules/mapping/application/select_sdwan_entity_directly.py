from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.mapping.domain.entities import MappingEntityResult
from app.modules.mapping.domain.enums import MappingEntityType
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class SelectSdwanEntityDirectlyCommand:
    mapping_scope_id: UUID
    mapping_result_id: UUID
    sdwan_entity_id: int


@dataclass(frozen=True, slots=True)
class SelectSdwanEntityDirectlyResult:
    mapping_result: MappingEntityResult


class SelectSdwanEntityDirectlyUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ) -> None:
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(
        self,
        command: SelectSdwanEntityDirectlyCommand,
    ) -> SelectSdwanEntityDirectlyResult:

        # -- find mapped canonical entity
        mapping_result: MappingEntityResult | None = await self.mapping_repo.get_result(
            scope_id=command.mapping_scope_id, result_id=command.mapping_result_id
        )
        if not mapping_result:
            raise MappingModuleNotFoundError(
                f"Mapping Result with id {command.mapping_result_id} not found"
            )

        scope = await self.mapping_repo.get_scope_by_id(command.mapping_scope_id)
        if scope is None:
            raise MappingModuleNotFoundError("Mapping scope not found")

        async with self.sdwan_gateway_provider.acquire(
            scope.csp_profile_id,
            scope.vpc_id,
        ) as sdwan_gateway:
            sdwan_entity: SdwanZone | SdwanService | SdwanAddrObject | None = None
            match mapping_result.entity_type:
                case MappingEntityType.ZONE:
                    sdwan_entity = await sdwan_gateway.get_zone(command.sdwan_entity_id)
                case MappingEntityType.SERVICE:
                    sdwan_entity = await sdwan_gateway.get_service(
                        command.sdwan_entity_id
                    )
                case MappingEntityType.ADDR:
                    sdwan_entity = await sdwan_gateway.get_addr_object(
                        command.sdwan_entity_id
                    )
                case _:
                    raise MappingModuleDomainValidationError(
                        f"Invalid entity type `{mapping_result.entity_type}`"
                    )

        if sdwan_entity is None:
            raise MappingModuleNotFoundError(
                f"Sdwan entity with id {command.sdwan_entity_id} "
                f"and type `{mapping_result.entity_type}` not found"
            )

        # -- assign sd-wan entity to mapped entity
        updated_mapping_result = mapping_result.select_direct(
            sdwan_entity_id=sdwan_entity.id,
        )
        await self.mapping_repo.save_result(updated_mapping_result)

        return SelectSdwanEntityDirectlyResult(mapping_result=updated_mapping_result)
