from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.errors import DomainValidationError, NotFoundError
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayPort
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort
from app.modules.execute.ports.mapping_reader.schemas import MappingScopeData
from app.modules.execute.ports.uow import ExecuteUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class PushExecutePlanRulesCommand:
    execute_plan_id: UUID


@dataclass(frozen=True, slots=True)
class PushExecutePlanRulesResult:
    rules: list[SdwanRuleDTO]


class PushExecutePlanRulesUseCase:
    """Push only NEW execute plan rules to SD-WAN."""

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
        command: PushExecutePlanRulesCommand,
    ) -> PushExecutePlanRulesResult:
        """Load target id from Mapping scope and push planned NEW rules."""
        execute_plan: ExecutePlan | None = await self.uow.plan_repo.get_plan(
            command.execute_plan_id
        )
        if not execute_plan:
            raise NotFoundError(f"Execute plan {command.execute_plan_id} not found")

        execute_plan_rules: list[ExecutePlanRule] = (
            await self.uow.plan_rule_repo.list_by_plan(
                plan_id=execute_plan.id,
                match_status=RuleMatchStatus.NEW,
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

        pushed_rules_ids: list[int] = await self.sdwan_gateway.push_rules(
            sdwan_target_id=mapping_scope.sdwan_target_id,
            plan_rules=execute_plan_rules,
        )

        pushed_rules: list[SdwanRuleDTO] = await self.sdwan_gateway.get_rules(
            pushed_rules_ids
        )

        return PushExecutePlanRulesResult(rules=pushed_rules)
