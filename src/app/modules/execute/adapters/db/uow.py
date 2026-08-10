from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.execute.adapters.db.repositories import (
    SqlAlchemyExecutePlanRepository,
    SqlAlchemyExecutePlanRuleRepository,
)
from app.modules.execute.ports.uow import ExecuteUnitOfWorkPort


class ExecuteUOW(SQLAlchemyUnitOfWork, ExecuteUnitOfWorkPort):
    async def __aenter__(self):
        await super().__aenter__()

        self.plan_repo = SqlAlchemyExecutePlanRepository(self.session)
        self.plan_rule_repo = SqlAlchemyExecutePlanRuleRepository(self.session)

        return self
