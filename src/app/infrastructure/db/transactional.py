from collections.abc import Callable
from functools import wraps
from typing import Protocol

from app.infrastructure.interfaces.db import IAsyncUnitOfWork


class IUseCaseWithUow(Protocol):
    uow: IAsyncUnitOfWork


def _set_nested_usecase_sessions(
    use_case: IUseCaseWithUow,
    uc_for_reuse_session: list[str] | None = None,
) -> None:
    if not uc_for_reuse_session:
        return
    for attr_name in uc_for_reuse_session:
        nested_uc = getattr(use_case, attr_name, None)
        if nested_uc and hasattr(nested_uc, "uow"):
            nested_uc.uow.session = use_case.uow.session


def async_transactional(
    uc_for_reuse_session: list[str] | None = None, *, read_only: bool = False
):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(use_case: IUseCaseWithUow, *args, **kwargs):
            owns_transaction: bool = use_case.uow.session is None

            if owns_transaction:
                async with use_case.uow:
                    _set_nested_usecase_sessions(use_case, uc_for_reuse_session)
                    result = await func(use_case, *args, **kwargs)
                    if not read_only:
                        await use_case.uow.commit()
                    return result

            async with use_case.uow(reuse_session=True):
                _set_nested_usecase_sessions(use_case, uc_for_reuse_session)
                result = await func(use_case, *args, **kwargs)
                return result

        return wrapper

    return decorator
