from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.mapping.ports.repositories import (
    MappingEntityResultRepositoryPort,
    MappingScopeRepositoryPort,
)


class MappingUnitOfWorkPort(IAsyncUnitOfWork):

    mapping_scope_repo: MappingScopeRepositoryPort
    mapping_result_repo: MappingEntityResultRepositoryPort
