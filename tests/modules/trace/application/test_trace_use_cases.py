"""Application-layer unit tests for trace use cases with fake UoW."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.trace.application.dto import (
    GetTraceByLineRangeQuery,
    SaveTraceRecordsCommand,
)
from app.modules.trace.application.use_cases.get_trace_by_line_range import (
    GetTraceByLineRangeUseCase,
)
from app.modules.trace.application.use_cases.save_trace_records import (
    SaveTraceRecordsUseCase,
)
from app.modules.trace.domain.exceptions import TraceModuleValidationError


class _FakeTraceRepo:
    def __init__(self) -> None:
        self.bulk_save_calls: list = []
        self.line_range_calls: list = []

    async def bulk_save(self, records):
        self.bulk_save_calls.append(records)

    async def get_by_line_range(self, **kwargs):
        self.line_range_calls.append(kwargs)
        return []


class _FakeTraceUoW:
    def __init__(self, repo: _FakeTraceRepo) -> None:
        self.session = None
        self.trace_raw_to_canonical = repo
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __call__(self, reuse_session=False):
        return self

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_save_trace_records_empty_list_skips_repository() -> None:
    repo = _FakeTraceRepo()
    use_case = SaveTraceRecordsUseCase(_FakeTraceUoW(repo))

    result = await use_case.execute(SaveTraceRecordsCommand(records=[]))

    assert result.written == 0
    assert repo.bulk_save_calls == []


@pytest.mark.asyncio
async def test_get_by_line_range_rejects_invalid_range_without_repo_call() -> None:
    repo = _FakeTraceRepo()
    use_case = GetTraceByLineRangeUseCase(_FakeTraceUoW(repo))

    with pytest.raises(TraceModuleValidationError, match="invalid line range"):
        await use_case.execute(
            GetTraceByLineRangeQuery(
                source_snapshot_id=uuid4(),
                line_from=10,
                line_to=1,
            )
        )

    assert repo.line_range_calls == []
