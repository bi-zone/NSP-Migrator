from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesQuery,
    GetExecutePlanRulesResult,
    GetExecutePlanRulesUseCase,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesQuery,
    GetSdwanRulesResult,
    GetSdwanRulesUseCase,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanCommand,
    PrepareExecutePlanResult,
    PrepareExecutePlanUseCase,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesCommand,
    PushExecutePlanRulesResult,
    PushExecutePlanRulesUseCase,
)
from app.modules.execute.di.dependencies import (
    get_execute_plan_rules_use_case,
    get_prepare_execute_plan_use_case,
    get_push_execute_plan_rules_use_case,
    get_sdwan_rules_use_case,
)
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.http.schemas import (
    ExecutePlanRuleResponse,
    PreparedExecutePlanResponse,
    SdwanRuleResponse,
)

execute_router = APIRouter(prefix="/execute", tags=["execute"])


@execute_router.post("/plans")
async def prepare_execute_plan(
    mapping_scope_id: UUID,
    prepare_execute_plan_use_case: PrepareExecutePlanUseCase = Depends(
        get_prepare_execute_plan_use_case
    ),
) -> PreparedExecutePlanResponse:
    result: PrepareExecutePlanResult = await prepare_execute_plan_use_case.execute(
        command=PrepareExecutePlanCommand(
            mapping_scope_id=mapping_scope_id,
        )
    )
    return PreparedExecutePlanResponse.model_validate(result)


@execute_router.get("/plans/{execute_plan_id}/rules")
async def get_execute_plan_rules(
    execute_plan_id: UUID,
    match_status: RuleMatchStatus | None = None,
    get_plan_rules_use_case: GetExecutePlanRulesUseCase = Depends(
        get_execute_plan_rules_use_case
    ),
) -> list[ExecutePlanRuleResponse]:
    result: GetExecutePlanRulesResult = await get_plan_rules_use_case.execute(
        query=GetExecutePlanRulesQuery(
            execute_plan_id=execute_plan_id,
            match_status=match_status,
        )
    )
    return [ExecutePlanRuleResponse.model_validate(rule) for rule in result.plan_rules]


@execute_router.post("/plans/{execute_plan_id}/push-rules")
async def push_execute_plan_rules(
    execute_plan_id: UUID,
    push_execute_plan_rules_use_case: PushExecutePlanRulesUseCase = Depends(
        get_push_execute_plan_rules_use_case
    ),
) -> list[SdwanRuleResponse]:
    result: PushExecutePlanRulesResult = await push_execute_plan_rules_use_case.execute(
        command=PushExecutePlanRulesCommand(execute_plan_id=execute_plan_id)
    )
    return [SdwanRuleResponse.model_validate(rule) for rule in result.rules]


@execute_router.get("/sdwan/rules")
async def get_sdwan_rules(
    rules_ids: list[int] = Query(default_factory=list),
    get_sdwan_rules_use_case: GetSdwanRulesUseCase = Depends(get_sdwan_rules_use_case),
) -> list[SdwanRuleResponse]:
    result: GetSdwanRulesResult = await get_sdwan_rules_use_case.execute(
        query=GetSdwanRulesQuery(rules_ids=rules_ids)
    )
    return [SdwanRuleResponse.model_validate(rule) for rule in result.rules]
