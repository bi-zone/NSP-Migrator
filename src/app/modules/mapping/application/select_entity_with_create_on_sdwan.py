from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.integrations.sdwan_csp_api.gateways.models import SdwanAddrObject, SdwanService
from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintCommand,
    RefreshMappingScopeCatalogFingerprintUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import MappingEntityType
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.port import CanonicalReaderPort
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalService,
    CanonicalServiceKind,
)
from app.modules.mapping.ports.gateways import (
    CreateAddrObjectPayload,
    CreateServicePayload,
    MappingSDWANGatewayProviderPort,
)
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class SelectEntityWithCreateOnSdwanCommand:
    mapping_scope_id: UUID
    mapping_result_id: UUID
    refresh_catalog_fingerprint: bool = True


@dataclass(frozen=True, slots=True)
class SelectEntityWithCreateOnSdwanResult:
    mapping_result: MappingEntityResult
    catalog_fingerprint_changed: bool


class SelectEntityWithCreateOnSdwanUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
        canonical_reader: CanonicalReaderPort,
        refresh_mapping_scope_catalog_fingerprint: RefreshMappingScopeCatalogFingerprintUseCase,
    ) -> None:
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider
        self.canonical_reader = canonical_reader
        self.refresh_mapping_scope_catalog_fingerprint = (
            refresh_mapping_scope_catalog_fingerprint
        )

    async def execute(  # noqa: C901
        self,
        command: SelectEntityWithCreateOnSdwanCommand,
    ) -> SelectEntityWithCreateOnSdwanResult:

        mapping_result: MappingEntityResult | None = await self.mapping_repo.get_result(
            scope_id=command.mapping_scope_id, result_id=command.mapping_result_id
        )
        if not mapping_result:
            raise MappingModuleNotFoundError(
                f"Mapping Result with id {command.mapping_result_id} does not exist"
            )

        # -- ZONE - not supported
        if mapping_result.entity_type == MappingEntityType.ZONE:
            raise ValueError("Zone can't be created automatically on SD-WAN")

        mapping_scope: MappingScope | None = await self.mapping_repo.get_scope_by_id(
            scope_id=command.mapping_scope_id,
        )
        if not mapping_scope:
            raise ValueError(
                f"Mapping scope {mapping_result.mapping_scope_id} not found"
            )

        # -- ADDR OBJ
        if mapping_result.entity_type == MappingEntityType.ADDR:
            canonical_addr_obj: CanonicalAddrObject | None = (  # fmt: off
                await self.canonical_reader.get_canonical_addr_object(
                    canonical_snapshot_id=mapping_scope.canonical_snapshot_id,
                    canonical_object_id=mapping_result.canonical_entity_id,
                )
            )
            if not canonical_addr_obj:
                raise ValueError(
                    f"Canonical addr obj {mapping_result.canonical_entity_id} not found"
                )

            addr_object_type_map = {
                CanonicalAddrObjKind.HOST: SdwanAddrObjectType.HOST,
                CanonicalAddrObjKind.SUBNET: SdwanAddrObjectType.PREFIX,
                CanonicalAddrObjKind.FQDN: SdwanAddrObjectType.FQDN,
                CanonicalAddrObjKind.RANGE: SdwanAddrObjectType.IP_RANGE,
            }
            if canonical_addr_obj.kind not in addr_object_type_map:
                raise ValueError(
                    f"Addr object kind `{canonical_addr_obj.kind}` "
                    f"not supported for auto-creation"
                )

            async with self.sdwan_gateway_provider.acquire(
                mapping_scope.csp_profile_id,
                mapping_scope.vpc_id,
            ) as sdwan_gateway:
                created_addr_obj: SdwanAddrObject = (
                    await sdwan_gateway.create_addr_object(
                        payload=CreateAddrObjectPayload(
                            type=addr_object_type_map[canonical_addr_obj.kind],  # type: ignore
                            prefix=canonical_addr_obj.cidr,
                            host=(
                                canonical_addr_obj.cidr.split("/")[0]
                                if canonical_addr_obj.cidr
                                else None
                            ),
                            fqdn=canonical_addr_obj.fqdn,
                            ip_range_from=canonical_addr_obj.range_start,
                            ip_range_to=canonical_addr_obj.range_end,
                        ),
                    )
                )

            # -- assign created sd-wan entity to mapped entity
            updated_mapping_result = mapping_result.select_created(created_addr_obj.id)

        # -- SERVICE
        elif mapping_result.entity_type == MappingEntityType.SERVICE:
            canonical_service: CanonicalService | None = (  # fmt: off
                await self.canonical_reader.get_canonical_service(
                    canonical_snapshot_id=mapping_scope.canonical_snapshot_id,
                    canonical_object_id=mapping_result.canonical_entity_id,
                )
            )
            if not canonical_service:
                raise ValueError(
                    f"Canonical service {mapping_result.canonical_entity_id} not found"
                )

            service_proto_map = {  # TODO: icmp later
                CanonicalServiceKind.TCP: SdwanServiceL4Proto.TCP,
                CanonicalServiceKind.UDP: SdwanServiceL4Proto.UDP,
            }

            if canonical_service.kind not in service_proto_map:
                raise ValueError(
                    f"Service proto `{canonical_service.kind}` "
                    f"not supported for auto-creation"
                )

            async with self.sdwan_gateway_provider.acquire(
                mapping_scope.csp_profile_id,
                mapping_scope.vpc_id,
            ) as sdwan_gateway:
                created_service: SdwanService = await sdwan_gateway.create_service(
                    payload=CreateServicePayload(
                        name=canonical_service.name,
                        l4_proto=service_proto_map[
                            canonical_service.kind  # type: ignore
                        ],  # `protocol` field not usable here
                        port_start=canonical_service.port_from,
                        port_end=canonical_service.port_to,
                        icmp_codes=None,
                    )
                )

            # -- assign created sd-wan entity to mapped entity
            updated_mapping_result = mapping_result.select_created(
                sdwan_entity_id=created_service.id,
            )

        else:
            raise MappingModuleDomainValidationError(
                f"Unexpected entity type `{mapping_result.entity_type}`"
            )

        await self.mapping_repo.save_result(updated_mapping_result)

        catalog_fingerprint_changed = False
        if command.refresh_catalog_fingerprint:
            refresh_result = (
                await self.refresh_mapping_scope_catalog_fingerprint.execute(
                    RefreshMappingScopeCatalogFingerprintCommand(
                        mapping_scope_id=mapping_scope.id
                    )
                )
            )
            catalog_fingerprint_changed = refresh_result.catalog_fingerprint_changed

        return SelectEntityWithCreateOnSdwanResult(
            mapping_result=updated_mapping_result,
            catalog_fingerprint_changed=catalog_fingerprint_changed,
        )
