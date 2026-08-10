from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import (
    PlannedRuleDraft,
    RuleCompareResult,
    SdwanPolicyCatalog,
)
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayPort
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort
from app.modules.execute.ports.mapping_reader.schemas import (
    MappedRuleData,
    MappingScopeData,
)
from app.modules.execute.ports.uow import ExecuteUnitOfWorkPort
from app.modules.execute.services.rules_comparer import RulesComparer


@dataclass(frozen=True, slots=True)
class PrepareExecutePlanCommand:
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class PrepareExecutePlanResult:
    id: UUID
    mapping_scope_id: UUID
    sdwan_target_id: str
    created_at: datetime
    total_rules: int
    new_rules: int
    matched_rules: int
    covered_rules: int
    errors_through_match: int


class PrepareExecutePlanUseCase:
    """Build and persist execute plan for one Mapping scope."""

    def __init__(
        self,
        uow: ExecuteUnitOfWorkPort,
        sdwan_gateway: ExecuteSDWANGatewayPort,
        mapping_reader: MappingReaderPort,
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway
        self.mapping_reader = mapping_reader

    @async_transactional(read_only=False)
    async def execute(
        self,
        command: PrepareExecutePlanCommand,
    ) -> PrepareExecutePlanResult:
        """Prepare plan rules and compare them with runtime SD-WAN catalog."""
        mapping_scope: MappingScopeData = (
            await self.mapping_reader.get_mapping_scope_data(
                mapping_scope_id=command.mapping_scope_id,
            )
        )
        mapped_rules_data: list[MappedRuleData] = (
            await self.mapping_reader.get_mapping_scope_rules(command.mapping_scope_id)
        )

        drafts_by_mapping_rule_id: dict[UUID, PlannedRuleDraft] = {
            mapped_rule_data.id: self._build_draft(mapped_rule_data)
            for mapped_rule_data in mapped_rules_data
        }

        extra_zone_ids, extra_service_ids, extra_addr_object_ids = (
            self._collect_rule_refs(drafts_by_mapping_rule_id.values())
        )

        sdwan_policy_catalog: SdwanPolicyCatalog = (
            await self.sdwan_gateway.get_sdwan_policy_catalog(
                sdwan_target_id=mapping_scope.sdwan_target_id,
                extra_zone_ids=extra_zone_ids,
                extra_service_ids=extra_service_ids,
                extra_addr_object_ids=extra_addr_object_ids,
            )
        )

        execute_plan = ExecutePlan.create(mapping_scope_id=command.mapping_scope_id)
        await self.uow.plan_repo.add_plan(execute_plan)

        rules_comparer = RulesComparer(catalog=sdwan_policy_catalog)

        execute_plan_rules: list[ExecutePlanRule] = []
        for mapping_scope_rule_id, draft in drafts_by_mapping_rule_id.items():
            match_result: RuleCompareResult = rules_comparer.compare_rule(draft)

            execute_plan_rules.append(
                ExecutePlanRule.create(
                    execute_plan_id=execute_plan.id,
                    mapping_scope_rule_id=mapping_scope_rule_id,
                    draft=draft,
                    match_status=match_result.match_status,
                    matched_sdwan_rule_id=match_result.matched_sdwan_rule_id,
                    match_info=match_result.match_info,
                )
            )

        await self.uow.plan_rule_repo.add_plan_rules_bulk(execute_plan_rules)

        return PrepareExecutePlanResult(
            id=execute_plan.id,
            mapping_scope_id=execute_plan.mapping_scope_id,
            sdwan_target_id=mapping_scope.sdwan_target_id,
            created_at=execute_plan.created_at,
            total_rules=len(execute_plan_rules),
            new_rules=sum(
                1
                for rule in execute_plan_rules
                if rule.match_status == RuleMatchStatus.NEW
            ),
            matched_rules=sum(
                1
                for rule in execute_plan_rules
                if rule.match_status == RuleMatchStatus.EXACT_MATCH
            ),
            covered_rules=sum(
                1
                for rule in execute_plan_rules
                if rule.match_status == RuleMatchStatus.COVERED_MATCH
            ),
            errors_through_match=sum(
                1
                for rule in execute_plan_rules
                if rule.match_status == RuleMatchStatus.MATCH_ERROR
            ),
        )

    def _build_draft(self, mapped_rule_data: MappedRuleData) -> PlannedRuleDraft:
        """Convert Mapping rule DTO into execute PlannedRuleDraft."""
        return PlannedRuleDraft(
            action=SdwanRuleAction(mapped_rule_data.action),
            src_zones=mapped_rule_data.src_zones,
            dst_zones=mapped_rule_data.dst_zones,
            src_addr_objects=mapped_rule_data.src_addr_objects,
            dst_addr_objects=mapped_rule_data.dst_addr_objects,
            services=mapped_rule_data.services,
        )

    def _collect_rule_refs(
        self,
        drafts: Iterable[PlannedRuleDraft],
    ) -> tuple[set[int], set[int], set[int]]:
        """Collect SD-WAN object ids required to normalize planned drafts."""
        zone_ids: set[int] = set()
        service_ids: set[int] = set()
        addr_object_ids: set[int] = set()

        for draft in drafts:
            zone_ids.update(draft.src_zones)
            zone_ids.update(draft.dst_zones)
            service_ids.update(draft.services)
            addr_object_ids.update(draft.src_addr_objects)
            addr_object_ids.update(draft.dst_addr_objects)

        return zone_ids, service_ids, addr_object_ids
