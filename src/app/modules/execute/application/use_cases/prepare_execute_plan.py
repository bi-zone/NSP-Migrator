from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import (
    ExcludedExistingRule,
    PlannedRuleDraft,
    RuleCompareResult,
    SdwanPolicyCatalog,
)
from app.modules.execute.errors import ConflictError
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayProviderPort
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort
from app.modules.execute.ports.mapping_reader.schemas import (
    MappedRuleData,
    MappingScopeData,
)
from app.modules.execute.ports.repositories import ExecuteRepositoryPort
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
    excluded_existing_rules: tuple[ExcludedExistingRule, ...]


class PrepareExecutePlanUseCase:
    """Build and persist execute plan for one Mapping scope."""

    def __init__(
        self,
        execute_repo: ExecuteRepositoryPort,
        sdwan_gateway_provider: ExecuteSDWANGatewayProviderPort,
        mapping_reader: MappingReaderPort,
    ) -> None:
        self.execute_repo = execute_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider
        self.mapping_reader = mapping_reader

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
        mapped_rules_data: list[
            MappedRuleData
        ] = await self.mapping_reader.get_mapping_scope_rules(command.mapping_scope_id)

        sorted_mapped_rules_data = sorted(
            mapped_rules_data,
            key=lambda mapped_rule_data: mapped_rule_data.priority,
        )
        prepared_rules = [
            (mapped_rule_data, self._build_draft(mapped_rule_data))
            for mapped_rule_data in sorted_mapped_rules_data
        ]

        extra_zone_ids, extra_service_ids, extra_addr_object_ids = (
            self._collect_rule_refs(draft for _, draft in prepared_rules)
        )

        async with self.sdwan_gateway_provider.acquire(
            mapping_scope.csp_profile_id,
            mapping_scope.vpc_id,
        ) as sdwan_gateway:
            # -- check that catalog fingerprint not changed
            current_catalog: SdwanFullCatalog = (
                await sdwan_gateway.get_sdwan_full_catalog()
            )
            catalog_fingerprint = current_catalog.get_fingerprint()
            if catalog_fingerprint != mapping_scope.catalog_fingerprint:
                raise ConflictError(
                    "SD-WAN catalog changed after mapping. "
                    "Create a new mapping scope before preparing an execute plan."
                )
            # -- get policies with linked objects
            sdwan_policy_catalog: SdwanPolicyCatalog = (
                await sdwan_gateway.get_sdwan_policy_catalog(
                    sdwan_target_id=mapping_scope.sdwan_target_id,
                    extra_zone_ids=extra_zone_ids,
                    extra_service_ids=extra_service_ids,
                    extra_addr_object_ids=extra_addr_object_ids,
                )
            )

        execute_plan = ExecutePlan.create(
            mapping_scope_id=command.mapping_scope_id,
            catalog_fingerprint=catalog_fingerprint,
        )

        rules_comparer = RulesComparer(catalog=sdwan_policy_catalog)

        execute_plan_rules: list[ExecutePlanRule] = []
        for mapped_rule_data, draft in prepared_rules:
            match_result: RuleCompareResult = rules_comparer.compare_rule(draft)

            execute_plan_rules.append(
                ExecutePlanRule.create(
                    execute_plan_id=execute_plan.id,
                    mapping_scope_rule_id=mapped_rule_data.id,
                    priority=mapped_rule_data.priority,
                    draft=draft,
                    match_status=match_result.match_status,
                    matched_sdwan_rule_id=match_result.matched_sdwan_rule_id,
                    match_info=match_result.match_info,
                    coverage_details=match_result.coverage_details,
                )
            )

        await self.execute_repo.add_plan_with_rules(
            plan=execute_plan,
            rules=execute_plan_rules,
        )

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
            excluded_existing_rules=rules_comparer.excluded_existing_rules,
        )

    def _build_draft(self, mapped_rule_data: MappedRuleData) -> PlannedRuleDraft:
        """Convert Mapping rule DTO into execute PlannedRuleDraft."""
        return PlannedRuleDraft(
            name=mapped_rule_data.name,
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
