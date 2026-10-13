from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.execute.application.dto import (
    CommitInfoDTO,
    PushRuleResultDTO,
    SdwanRuleDTO,
)
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import (
    ExecutePlanPushStatus,
    RuleMatchStatus,
    RulePushStatus,
)
from app.modules.execute.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayProviderPort
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort
from app.modules.execute.ports.mapping_reader.schemas import MappingScopeData
from app.modules.execute.ports.reports_writer import ReportsWriterPort
from app.modules.execute.ports.repositories import ExecuteRepositoryPort


@dataclass(frozen=True, slots=True)
class PushExecutePlanRulesCommand:
    execute_plan_id: UUID


@dataclass(frozen=True, slots=True)
class PushExecutePlanRulesResult:
    rules: list[SdwanRuleDTO]
    push_results: list[PushRuleResultDTO]
    commit_info: CommitInfoDTO


class PushExecutePlanRulesUseCase:
    """Push only NEW execute plan rules to SD-WAN."""

    def __init__(
        self,
        execute_repo: ExecuteRepositoryPort,
        sdwan_gateway_provider: ExecuteSDWANGatewayProviderPort,
        mapping_reader: MappingReaderPort,
        reports_writer: ReportsWriterPort,
    ) -> None:
        self.execute_repo = execute_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider
        self.mapping_reader = mapping_reader
        self.reports_writer = reports_writer

    async def execute(
        self,
        command: PushExecutePlanRulesCommand,
    ) -> PushExecutePlanRulesResult:
        """Load target id from Mapping scope and push planned NEW rules."""
        execute_plan: ExecutePlan | None = await self.execute_repo.get_plan(
            command.execute_plan_id
        )
        if not execute_plan:
            raise NotFoundError(f"Execute plan {command.execute_plan_id} not found")
        if execute_plan.push_status == ExecutePlanPushStatus.EXECUTED:
            raise DomainValidationError(
                f"Execute plan {execute_plan.id} was already pushed. "
                "Prepare a new execute plan before push."
            )

        execute_plan_rules: list[ExecutePlanRule] = (  # fmt: no
            await self.execute_repo.list_plan_rules(  # fmt: no
                plan_id=execute_plan.id,
                match_status=RuleMatchStatus.NEW,
                push_statuses={RulePushStatus.PENDING},
            )
        )
        if not execute_plan_rules:
            raise DomainValidationError(
                f"Execute plan {execute_plan.id} has no rules for push"
            )

        mapping_scope: MappingScopeData = (
            await self.mapping_reader.get_mapping_scope_data(
                execute_plan.mapping_scope_id
            )
        )
        # -- if mapping scope was changed after already prepared plan by previous version of this mapping scope
        if mapping_scope.catalog_fingerprint != execute_plan.catalog_fingerprint:
            raise ConflictError(
                "Mapping scope catalog baseline changed after preparing the execute "
                "plan. Prepare a new execute plan before push."
            )

        async with self.sdwan_gateway_provider.acquire(
            mapping_scope.csp_profile_id,
            mapping_scope.vpc_id,
        ) as sdwan_gateway:
            # -- check that sdwan catalog is actual
            current_catalog: SdwanFullCatalog = (
                await sdwan_gateway.get_sdwan_full_catalog()
            )
            if current_catalog.get_fingerprint() != execute_plan.catalog_fingerprint:
                raise ConflictError(
                    "SD-WAN catalog changed after preparing the execute plan. "
                    "Prepare a new execute plan before push."
                )
            await self.execute_repo.update_plan(plan=execute_plan.mark_push_executed())
            # -- push rules
            push_results: list[PushRuleResultDTO] = await sdwan_gateway.push_rules(
                sdwan_target_id=mapping_scope.sdwan_target_id,
                plan_rules=sorted(execute_plan_rules, key=lambda rule: rule.priority),
                priority=mapping_scope.rules_priority,
            )
            # -- mark plan rule as succeeded or failed
            plan_rules_by_id = {rule.id: rule for rule in execute_plan_rules}
            for push_result in push_results:
                plan_rule = plan_rules_by_id[push_result.execute_plan_rule_id]
                updated_plan_rule = (
                    plan_rule.mark_push_succeeded(push_result.sdwan_rule_id)
                    if push_result.sdwan_rule_id is not None
                    else plan_rule.mark_push_failed(push_result.error or "Push failed")
                )
                await self.execute_repo.update_plan_rule(rule=updated_plan_rule)

            pushed_rule_ids: list[int] = [
                result.sdwan_rule_id
                for result in push_results
                if result.sdwan_rule_id is not None
            ]
            pushed_rules: list[SdwanRuleDTO] = []
            if pushed_rule_ids:
                pushed_rules = await sdwan_gateway.get_rules(pushed_rule_ids)

            # -- commit changes on csp
            commit_info: CommitInfoDTO = await sdwan_gateway.commit_csp_changes()

        all_plan_rules = await self.execute_repo.list_plan_rules(
            plan_id=execute_plan.id,
        )
        await self.reports_writer.save_report(
            scope_title=mapping_scope.title,
            csp_profile_id=mapping_scope.csp_profile_id,
            vpc_id=mapping_scope.vpc_id,
            target_id=mapping_scope.sdwan_target_id,
            commit_id=commit_info.commit_id,
            plan_rules=all_plan_rules,
        )

        return PushExecutePlanRulesResult(
            rules=pushed_rules,
            push_results=push_results,
            commit_info=commit_info,
        )
