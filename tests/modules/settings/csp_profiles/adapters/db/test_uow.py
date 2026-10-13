from __future__ import annotations

import asyncio
from typing import Any, cast

from app.modules.settings.csp_profiles.adapters.db.uow import (
    CSPProfilesUnitOfWork,
)
from tests.modules.settings.csp_profiles.adapters.db.test_credential_store import _codec


class _FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0
        self.close_calls = 0

    async def rollback(self) -> None:
        self.rollback_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def create_session(self):
        return self.session


def test_uow_binds_one_session_and_rolls_back_both_stores() -> None:
    asyncio.run(_test_uow_binds_one_session_and_rolls_back_both_stores())


async def _test_uow_binds_one_session_and_rolls_back_both_stores() -> None:
    session = _FakeSession()
    uow = CSPProfilesUnitOfWork(
        cast(Any, _FakeSessionFactory(session)),
        _codec(),
    )

    try:
        async with uow:
            assert uow.profiles.session is session
            assert uow.credentials.session is session
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    assert session.rollback_calls == 1
    assert session.close_calls == 1
