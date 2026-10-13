"""HTTP boundary tests for canonical routes and composed rule query models."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.fastapi.error_handlers import register_exception_handlers
from app.modules.canonical.application.dto import PaginationDTO
from app.modules.canonical.di.dependencies import (
    get_canonical_object_use_case,
    get_canonical_rules_use_case,
    get_canonical_snapshot_use_case,
)
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.http.router import canonical_router
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleSearchScope,
    CanonicalRuleSortField,
)


class _NotFoundUseCase:
    def __init__(self, message: str) -> None:
        self.message = message

    async def execute(self, _query):
        raise CanonicalModuleNotFoundError(self.message)


class _ResultUseCase:
    def __init__(self, result) -> None:
        self.result = result

    async def execute(self, _query):
        return self.result


class _RecordingRulesUseCase:
    def __init__(self) -> None:
        self.query = None

    async def execute(self, query):
        self.query = query
        return SimpleNamespace(
            rules=[],
            pagination=PaginationDTO(
                limit=query.pagination.limit,
                offset=query.pagination.offset,
                total=0,
            ),
        )


def _snapshot_dto(*, snapshot_id: UUID | None = None):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=snapshot_id or uuid4(),
        source_snapshot_id=uuid4(),
        normalizer_code="cisco_asa",
        normalizer_version="1",
        status="success",
        zones_total=1,
        objects_total=2,
        rules_total=3,
        issues_total=4,
        created_at=now,
    )


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(canonical_router)
    return TestClient(app)


def test_get_snapshot_serializes_header_contract() -> None:
    snapshot_id = uuid4()
    client = _client()
    client.app.dependency_overrides[get_canonical_snapshot_use_case] = (
        lambda: _ResultUseCase(
            SimpleNamespace(snapshot=_snapshot_dto(snapshot_id=snapshot_id))
        )
    )

    response = client.get(f"/canonical/snapshots/{snapshot_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(snapshot_id),
        "source_snapshot_id": response.json()["source_snapshot_id"],
        "normalizer_code": "cisco_asa",
        "normalizer_version": "1",
        "status": "success",
        "zones_total": 1,
        "objects_total": 2,
        "rules_total": 3,
        "issues_total": 4,
        "created_at": response.json()["created_at"],
    }


def test_missing_snapshot_and_object_use_shared_404_error_contract() -> None:
    snapshot_id = uuid4()
    object_id = uuid4()
    client = _client()
    client.app.dependency_overrides[get_canonical_snapshot_use_case] = lambda: (
        _NotFoundUseCase(f"Canonical snapshot not found: {snapshot_id}")
    )
    client.app.dependency_overrides[get_canonical_object_use_case] = lambda: (
        _NotFoundUseCase(f"Canonical object not found: {object_id}")
    )

    snapshot_response = client.get(f"/canonical/snapshots/{snapshot_id}")
    object_response = client.get(
        f"/canonical/snapshots/{snapshot_id}/objects/{object_id}"
    )

    assert snapshot_response.status_code == 404
    assert snapshot_response.json()["code"] == "not_found"
    assert snapshot_response.json()["message"] == (
        f"Canonical snapshot not found: {snapshot_id}"
    )
    assert object_response.status_code == 404
    assert object_response.json()["code"] == "not_found"
    assert object_response.json()["message"] == (
        f"Canonical object not found: {object_id}"
    )


def test_rule_query_parameters_map_to_application_contract() -> None:
    snapshot_id = uuid4()
    rule_ids = [uuid4(), uuid4()]
    zone_ids = [uuid4(), uuid4()]
    object_ids = [uuid4(), uuid4()]
    recorder = _RecordingRulesUseCase()
    client = _client()
    client.app.dependency_overrides[get_canonical_rules_use_case] = lambda: recorder

    response = client.get(
        f"/canonical/snapshots/{snapshot_id}/rules",
        params=[
            ("limit", "25"),
            ("offset", "5"),
            ("rule_id", str(rule_ids[0])),
            ("rule_id", str(rule_ids[1])),
            ("search", "  payroll  "),
            ("search_scope", "objects"),
            ("action", "  permit  "),
            ("enabled", "false"),
            ("section", "  outside_in  "),
            ("operand_zone_id", str(zone_ids[0])),
            ("operand_zone_id", str(zone_ids[1])),
            ("operand_object_id", str(object_ids[0])),
            ("operand_object_id", str(object_ids[1])),
            ("sort_by", "name"),
            ("sort_dir", "desc"),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "rules": [],
        "pagination": {"limit": 25, "offset": 5, "total": 0},
    }
    query = recorder.query
    assert query.canonical_snapshot_id == snapshot_id
    assert query.pagination.limit == 25
    assert query.pagination.offset == 5
    assert query.filters.rule_ids == rule_ids
    assert query.filters.search == "payroll"
    assert query.filters.search_scope == CanonicalRuleSearchScope.OBJECTS
    assert query.filters.action == "permit"
    assert query.filters.enabled is False
    assert query.filters.section == "outside_in"
    assert query.filters.operand_zone_ids == zone_ids
    assert query.filters.operand_object_ids == object_ids
    assert query.sorting is not None
    assert query.sorting.field == CanonicalRuleSortField.NAME
    assert query.sorting.direction == "desc"


def test_blank_strings_are_omitted_and_sort_requires_explicit_field() -> None:
    snapshot_id = uuid4()
    recorder = _RecordingRulesUseCase()
    client = _client()
    client.app.dependency_overrides[get_canonical_rules_use_case] = lambda: recorder

    response = client.get(
        f"/canonical/snapshots/{snapshot_id}/rules",
        params={
            "search": "   ",
            "action": "   ",
            "section": "   ",
            "sort_dir": "desc",
        },
    )

    assert response.status_code == 200
    assert recorder.query.filters.search is None
    assert recorder.query.filters.action is None
    assert recorder.query.filters.section is None
    assert recorder.query.sorting is None


def test_rule_query_validation_rejects_invalid_and_unknown_values() -> None:
    snapshot_id = uuid4()
    recorder = _RecordingRulesUseCase()
    client = _client()
    client.app.dependency_overrides[get_canonical_rules_use_case] = lambda: recorder

    cases = [
        {"limit": "0"},
        {"limit": "201"},
        {"offset": "-1"},
        {"search_scope": "invalid"},
        {"sort_by": "created_at"},
        {"sort_dir": "sideways"},
        {"unknown_filter": "value"},
    ]
    for params in cases:
        response = client.get(
            f"/canonical/snapshots/{snapshot_id}/rules",
            params=params,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "request_validation_error"
        assert response.json()["message"] == "Request validation failed"


def test_openapi_exposes_flat_rule_filters_as_query_parameters() -> None:
    client = _client()
    operation = client.get("/openapi.json").json()["paths"][
        "/canonical/snapshots/{snapshot_id}/rules"
    ]["get"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}

    assert {
        "snapshot_id",
        "limit",
        "offset",
        "rule_id",
        "search",
        "search_scope",
        "action",
        "enabled",
        "section",
        "operand_zone_id",
        "operand_object_id",
        "sort_by",
        "sort_dir",
    } <= parameter_names
    assert "requestBody" not in operation
