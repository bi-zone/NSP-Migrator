from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.execute.ports.repositories import (
    ExecutePlanRepositoryPort,
    ExecutePlanRuleRepositoryPort,
)


class ExecuteUnitOfWorkPort(IAsyncUnitOfWork):
    plan_repo: ExecutePlanRepositoryPort
    plan_rule_repo: ExecutePlanRuleRepositoryPort
