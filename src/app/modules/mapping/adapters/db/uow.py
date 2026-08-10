from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.mapping.adapters.db.repositories import (
    SqlAlchemyMappingEntityResultRepository,
    SqlAlchemyMappingScopeRepository,
)
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


class MappingUOW(SQLAlchemyUnitOfWork, MappingUnitOfWorkPort):
    async def __aenter__(self):
        await super().__aenter__()

        self.mapping_scope_repo = SqlAlchemyMappingScopeRepository(self.session)
        self.mapping_result_repo = SqlAlchemyMappingEntityResultRepository(self.session)

        return self
