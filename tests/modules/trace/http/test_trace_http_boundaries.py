"""HTTP boundary tests for trace routes and list response contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.fastapi.error_handlers import register_exception_handlers
from app.modules.trace.di.dependencies import (
    get_trace_by_line_range_use_case,
    get_trace_for_canonical_snapshot_use_case,
    get_trace_for_entity_use_case,
    get_trace_for_source_snapshot_use_case,
)
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.exceptions import TraceModuleValidationError
from app.modules.trace.http.router import trace_router


class _ResultUseCase:
    def __init__(self, result) -> None:
        self.result = result
        self.query = None

    async def execute(self, query):
        self.query = query
        return self.result


class _ValidationUseCase:
    def __init__(self, message: str) -> None:
        self.message = message

    async def execute(self, _query):
        raise TraceModuleValidationError(self.message)


def _record_dto(
    *,
    record_id: UUID | None = None,
    canonical_kind: str = "rule",
    source_line_start: int = 1,
    source_line_end: int = 1,
):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=record_id or uuid4(),
        source_snapshot_id=uuid4(),
        canonical_snapshot_id=uuid4(),
        vendor_code="cisco_asa",
        normalizer_code="cisco_asa",
        normalizer_version="1",
        source_line_start=source_line_start,
        source_line_end=source_line_end,
        source_fragment="access-list ACL_IN",
        canonical_kind=canonical_kind,
        canonical_id=uuid4(),
        canonical_role=None,
        note=None,
        created_at=now,
    )


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(trace_router)
    return TestClient(app)


def test_list_requires_exactly_one_snapshot_id() -> None:
    client = _client()
    client.app.dependency_overrides[get_trace_for_canonical_snapshot_use_case] = (
        lambda: _ResultUseCase([])
    )
    client.app.dependency_overrides[get_trace_for_source_snapshot_use_case] = (
        lambda: _ResultUseCase([])
    )

    missing = client.get("/trace/raw-to-canonical")
    assert missing.status_code == 400
    assert "must be provided" in missing.json()["detail"]

    both = client.get(
        "/trace/raw-to-canonical",
        params={
            "canonical_snapshot_id": str(uuid4()),
            "source_snapshot_id": str(uuid4()),
        },
    )
    assert both.status_code == 400
    assert "only one" in both.json()["detail"]


def test_list_by_canonical_snapshot_forwards_filters_and_pagination() -> None:
    client = _client()
    use_case = _ResultUseCase([_record_dto(canonical_kind="object")])
    client.app.dependency_overrides[get_trace_for_canonical_snapshot_use_case] = (
        lambda: use_case
    )
    client.app.dependency_overrides[get_trace_for_source_snapshot_use_case] = (
        lambda: _ResultUseCase([])
    )

    snapshot_id = uuid4()
    response = client.get(
        "/trace/raw-to-canonical",
        params={
            "canonical_snapshot_id": str(snapshot_id),
            "canonical_kind": "object",
            "limit": 25,
            "offset": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["canonical_kind"] == "object"
    assert use_case.query.canonical_snapshot_id == snapshot_id
    assert use_case.query.canonical_kind == TraceCanonicalKind.OBJECT
    assert use_case.query.limit == 25
    assert use_case.query.offset == 5


def test_list_by_source_snapshot_uses_source_use_case() -> None:
    client = _client()
    canonical_uc = _ResultUseCase([])
    source_uc = _ResultUseCase([_record_dto()])
    client.app.dependency_overrides[get_trace_for_canonical_snapshot_use_case] = (
        lambda: canonical_uc
    )
    client.app.dependency_overrides[get_trace_for_source_snapshot_use_case] = (
        lambda: source_uc
    )

    source_snapshot_id = uuid4()
    response = client.get(
        "/trace/raw-to-canonical",
        params={"source_snapshot_id": str(source_snapshot_id)},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert source_uc.query.source_snapshot_id == source_snapshot_id
    assert canonical_uc.query is None


def test_by_entity_serializes_trace_record_response() -> None:
    client = _client()
    record = _record_dto(
        canonical_kind="object",
        source_line_start=20,
        source_line_end=23,
    )
    use_case = _ResultUseCase([record])
    client.app.dependency_overrides[get_trace_for_entity_use_case] = lambda: use_case

    response = client.get(
        "/trace/raw-to-canonical/by-entity",
        params={
            "canonical_kind": "object",
            "canonical_id": str(record.canonical_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(record.id)
    assert item["canonical_kind"] == "object"
    assert item["source_line_start"] == 20
    assert item["source_line_end"] == 23
    assert item["source_fragment"] == "access-list ACL_IN"
    assert item["vendor_code"] == "cisco_asa"
    assert use_case.query.canonical_kind == TraceCanonicalKind.OBJECT
    assert use_case.query.canonical_id == record.canonical_id


def test_by_lines_router_guard_rejects_inverted_range() -> None:
    client = _client()
    client.app.dependency_overrides[get_trace_by_line_range_use_case] = (
        lambda: _ResultUseCase([])
    )

    response = client.get(
        "/trace/raw-to-canonical/by-lines",
        params={
            "source_snapshot_id": str(uuid4()),
            "line_from": 10,
            "line_to": 1,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "line_to must be >= line_from"


def test_by_lines_maps_use_case_validation_error_to_400() -> None:
    client = _client()
    client.app.dependency_overrides[get_trace_by_line_range_use_case] = (
        lambda: _ValidationUseCase("invalid line range: from=10 to=1")
    )

    response = client.get(
        "/trace/raw-to-canonical/by-lines",
        params={
            "source_snapshot_id": str(uuid4()),
            "line_from": 1,
            "line_to": 5,
        },
    )

    assert response.status_code == 400
    assert "invalid line range" in response.json()["detail"]


def test_by_lines_happy_path_returns_items() -> None:
    client = _client()
    record = _record_dto(source_line_start=10, source_line_end=12)
    use_case = _ResultUseCase([record])
    client.app.dependency_overrides[get_trace_by_line_range_use_case] = (
        lambda: use_case
    )

    source_snapshot_id = uuid4()
    response = client.get(
        "/trace/raw-to-canonical/by-lines",
        params={
            "source_snapshot_id": str(source_snapshot_id),
            "line_from": 10,
            "line_to": 12,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source_line_start"] == 10
    assert use_case.query.source_snapshot_id == source_snapshot_id
    assert use_case.query.line_from == 10
    assert use_case.query.line_to == 12


def test_list_response_total_equals_page_size_not_db_count() -> None:
    """Document current contract: total == len(items) for the returned page."""
    client = _client()
    rows = [_record_dto() for _ in range(3)]
    client.app.dependency_overrides[get_trace_for_canonical_snapshot_use_case] = (
        lambda: _ResultUseCase(rows)
    )
    client.app.dependency_overrides[get_trace_for_source_snapshot_use_case] = (
        lambda: _ResultUseCase([])
    )

    response = client.get(
        "/trace/raw-to-canonical",
        params={"canonical_snapshot_id": str(uuid4()), "limit": 3, "offset": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(body["items"]) == 3
