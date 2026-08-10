from collections.abc import Sequence
from typing import Any, Protocol, Self, TypeVar


class ISessionFactory(Protocol):
    def create_session(self) -> Any: ...


TEntity = TypeVar("TEntity")
ID = TypeVar("ID")


class IAsyncRepository(Protocol[TEntity, ID]):
    async def add(self, entity: TEntity) -> TEntity: ...

    async def get_list(self) -> Sequence[TEntity]: ...

    async def get_by_id(self, entity_id: ID) -> TEntity | None: ...

    async def delete_by_id(self, entity_id: ID) -> None: ...


class IAsyncUnitOfWork(Protocol):
    session: object

    def __call__(self, *, reuse_session: bool = False): ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def flush(self) -> None: ...

    async def refresh(self, item: object) -> None: ...
