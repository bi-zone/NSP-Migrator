from uuid import UUID

from app.modules.canonical.application.dto import CanonicalObjectDTO
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
    GetCanonicalObjectResult,
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    CanonicalRuleFilters,
    GetCanonicalRuleScopeQuery,
    GetCanonicalRuleScopeResult,
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.domain import ObjectFamily as CanonicalObjectFamily
from app.modules.mapping.domain.exceptions import (
    MappingModuleError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.port import (
    CanonicalReaderPort,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalRule,
    CanonicalRuleAction,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalService,
    CanonicalServiceKind,
    CanonicalZone,
)


class CanonicalReader(CanonicalReaderPort):
    def __init__(
        self,
        get_canonical_rules_scope: GetCanonicalRuleScopeUseCase,
        get_canonical_object: GetCanonicalObjectUseCase,
    ):
        self.get_canonical_rules_scope = get_canonical_rules_scope
        self.get_canonical_object = get_canonical_object

    async def get_canonical_scope_entities_data(
        self,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> CanonicalScopeEntities:
        # -- request for canonical rules and sub-entities
        if not canonical_rules_ids:
            raise MappingModuleError("Canonical rules ids must be provided")

        result: GetCanonicalRuleScopeResult = (
            await self.get_canonical_rules_scope.execute(
                query=GetCanonicalRuleScopeQuery(
                    canonical_snapshot_id=canonical_snapshot_id,
                    filters=CanonicalRuleFilters(rule_ids=canonical_rules_ids),
                )
            )
        )

        result_rules = result.rules
        if not result_rules:
            raise MappingModuleNotFoundError(
                f"No found canonical rules for provided ids list: {canonical_rules_ids}"
            )

        if len(result_rules) != len(canonical_rules_ids):
            request_ids: set[UUID] = set(canonical_rules_ids)
            response_ids: set[UUID] = set(r.id for r in result_rules)
            not_found_ids: set[UUID] = request_ids - response_ids
            raise MappingModuleNotFoundError(
                f"Not found canonical rules for ids: {not_found_ids}"
            )

        # -- serialize results
        canonical_zones: list[CanonicalZone] = [
            CanonicalZone(
                id=z.id,
                name=z.name,
                zone_key=z.zone_key,
            )
            for z in result.zones
        ]

        canonical_addr_objects: list[CanonicalAddrObject] = []
        canonical_services: list[CanonicalService] = []

        for canonical_object in result.objects:
            if canonical_object.object_family == CanonicalObjectFamily.ADDR:
                canonical_addr_objects.append(
                    self._map_canonical_obj_to_addr(canonical_object)
                )

            elif canonical_object.object_family == CanonicalObjectFamily.SERVICE:
                canonical_services.append(
                    self._map_canonical_obj_to_service(canonical_object)
                )

            else:
                raise MappingModuleError(
                    f"Unprocessable canonical object family "
                    f"{canonical_object.object_family}"
                )

        return CanonicalScopeEntities(
            zones=canonical_zones,
            addr_objects=canonical_addr_objects,
            services=canonical_services,
        )

    @staticmethod
    def _map_canonical_obj_to_addr(obj: CanonicalObjectDTO) -> CanonicalAddrObject:
        return CanonicalAddrObject(
            id=obj.id,
            kind=CanonicalAddrObjKind(obj.object_kind),
            name=obj.name,
            parent_id=obj.parent_id,
            parent_ids=obj.parent_ids,
            cidr=obj.cidr,
            range_start=obj.range_start,
            range_end=obj.range_end,
            fqdn=obj.fqdn,
        )

    @staticmethod
    def _map_canonical_obj_to_service(obj: CanonicalObjectDTO) -> CanonicalService:
        return CanonicalService(
            id=obj.id,
            kind=CanonicalServiceKind(obj.object_kind),
            name=obj.name,
            parent_id=obj.parent_id,
            parent_ids=obj.parent_ids,
            protocol=obj.protocol,
            port_from=obj.port_from,
            port_to=obj.port_to,
            icmp_type=obj.icmp_type,
            icmp_code=obj.icmp_code,
        )

    async def _get_canonical_object(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalObjectDTO:
        try:
            result: GetCanonicalObjectResult = await self.get_canonical_object.execute(
                query=GetCanonicalObjectQuery(
                    canonical_snapshot_id=canonical_snapshot_id,
                    object_id=canonical_object_id,
                    include_members=False,
                )
            )
        except Exception as e:
            if "not found" in str(e):
                raise MappingModuleNotFoundError(
                    f"Not found canonical addr object {canonical_object_id}"
                )
            raise e

        return result.object

    async def get_canonical_addr_object(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalAddrObject | None:

        canonical_object: CanonicalObjectDTO = await self._get_canonical_object(
            canonical_snapshot_id, canonical_object_id
        )

        if canonical_object.object_family != CanonicalObjectFamily.ADDR:
            raise MappingModuleNotFoundError(
                f"Canonical object {canonical_object_id} is not ADDR"
            )

        return self._map_canonical_obj_to_addr(canonical_object)

    async def get_canonical_service(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalService | None:

        canonical_object: CanonicalObjectDTO = await self._get_canonical_object(
            canonical_snapshot_id, canonical_object_id
        )

        if canonical_object.object_family != CanonicalObjectFamily.SERVICE:
            raise MappingModuleNotFoundError(
                f"Canonical object {canonical_object_id} is not SERVICE"
            )

        return self._map_canonical_obj_to_service(canonical_object)

    async def get_canonical_scope_rules(
        self, canonical_snapshot_id: UUID, canonical_rules_ids: list[UUID]
    ) -> list[CanonicalRule]:
        """
        Return canonical rules with operands converted to mapping-local models.
        """

        canonical_result: GetCanonicalRuleScopeResult = (
            await self.get_canonical_rules_scope.execute(
                query=GetCanonicalRuleScopeQuery(
                    canonical_snapshot_id=canonical_snapshot_id,
                    filters=CanonicalRuleFilters(rule_ids=canonical_rules_ids),
                )
            )
        )

        return [
            CanonicalRule(
                id=rule.id,
                canonical_snapshot_id=rule.canonical_snapshot_id,
                name=rule.name,
                action=CanonicalRuleAction(rule.action),
                operands=[
                    CanonicalRuleOperand(
                        id=operand.id,
                        rule_id=operand.rule_id,
                        role=CanonicalRuleOperandRole(
                            operand.operand_role.value,
                        ),
                        target_zone_id=operand.target_zone_id,
                        target_object_id=operand.target_object_id,
                    )
                    for operand in rule.operands or []
                ],
            )
            for rule in canonical_result.rules
        ]
