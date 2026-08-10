from fastapi import Request

from app.di.dependencies import get_di_container
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesUseCase,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesUseCase,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanUseCase,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesUseCase,
)
from app.modules.execute.di.container import ExecuteModuleContainer


def get_execute_module_container(request: Request) -> ExecuteModuleContainer:
    return get_di_container(request).execute_module()


# -- use cases
def get_prepare_execute_plan_use_case(request: Request) -> PrepareExecutePlanUseCase:
    return get_execute_module_container(request).prepare_execute_plan_use_case()


def get_push_execute_plan_rules_use_case(
    request: Request,
) -> PushExecutePlanRulesUseCase:
    return get_execute_module_container(request).push_execute_plan_rules_use_case()


def get_execute_plan_rules_use_case(request: Request) -> GetExecutePlanRulesUseCase:
    return get_execute_module_container(request).get_execute_plan_rules_use_case()


def get_sdwan_rules_use_case(request: Request) -> GetSdwanRulesUseCase:
    return get_execute_module_container(request).get_sdwan_rules_use_case()
