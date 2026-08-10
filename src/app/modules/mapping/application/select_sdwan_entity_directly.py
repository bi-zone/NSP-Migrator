from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
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
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class SelectSdwanEntityDirectlyCommand:

    mapping_result_id: UUID
    sdwan_entity_id: int


@dataclass(frozen=True, slots=True)
class SelectSdwanEntityDirectlyResult:

    mapping_result: MappingEntityResult


class SelectSdwanEntityDirectlyUseCase:
    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
        sdwan_gateway: MappingSDWANGatewayPort,
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway

    @async_transactional(read_only=False)
    async def execute(
        self,
        command: SelectSdwanEntityDirectlyCommand,
    ) -> SelectSdwanEntityDirectlyResult:

        # -- find mapped canonical entity
        mapping_result: MappingEntityResult | None = (
            await self.uow.mapping_result_repo.get_result_by_id(
                result_id=command.mapping_result_id
            )
        )
        if not mapping_result:
            raise MappingModuleNotFoundError(
                f"Mapping Result with id {command.mapping_result_id} not found"
            )

        # -- get sd-wan entity
        sdwan_entity: SdwanZone | SdwanService | SdwanAddrObject | None = None

        match mapping_result.entity_type:

            case MappingEntityType.ZONE:
                sdwan_entity = await self.sdwan_gateway.get_zone(
                    command.sdwan_entity_id
                )

            case MappingEntityType.SERVICE:
                sdwan_entity = await self.sdwan_gateway.get_service(
                    command.sdwan_entity_id
                )

            case MappingEntityType.ADDR:
                sdwan_entity = await self.sdwan_gateway.get_addr_object(
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
        await self.uow.mapping_result_repo.save_result(updated_mapping_result)

        return SelectSdwanEntityDirectlyResult(mapping_result=updated_mapping_result)
