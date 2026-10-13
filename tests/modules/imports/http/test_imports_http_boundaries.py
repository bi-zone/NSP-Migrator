from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ModuleNotFoundError:
    FastAPI = None
    TestClient = None
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(
    not HAS_FASTAPI,
    reason="fastapi is not installed in current test environment",
)


def _source_dto(*, source_id: UUID, name: str):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=source_id,
        vendor_code="cisco_asa",
        name=name,
        description="test source",
        active=True,
        created_at=now,
        updated_at=now,
    )


class _CreateSourceUseCase:
    def __init__(self, *, created: bool):
        self.created = created

    async def execute(self, _command):
        return SimpleNamespace(
            source=_source_dto(source_id=uuid4(), name="edge-fw"),
            created=self.created,
        )


class _GetSourceUseCase:
    def __init__(self, source):
        self.source = source

    async def execute(self, _query):
        return SimpleNamespace(source=self.source)


class _ListSourcesUseCase:
    async def execute(self, _query):
        return SimpleNamespace(
            sources=[
                _source_dto(source_id=uuid4(), name="edge-fw"),
                _source_dto(source_id=uuid4(), name="branch-fw"),
            ]
        )


class _ListVendorsUseCase:
    async def execute(self, _query):
        now = datetime.now(UTC)
        return SimpleNamespace(
            vendors=[
                SimpleNamespace(
                    code="cisco_asa",
                    display_name="Cisco ASA",
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            ]
        )


class _GetArtifactUseCase:
    def __init__(self, *, should_raise: bool = False):
        self.should_raise = should_raise

    async def execute(self, _query):
        if self.should_raise:
            from app.modules.imports.errors import SourceArtifactNotFoundError

            raise SourceArtifactNotFoundError("artifact is missing")
        return SimpleNamespace(
            source_snapshot_id=uuid4(),
            raw_text="line1\nline2",
            line_count=2,
            size_bytes=11,
        )


class _MappingUseCase:
    def __init__(self, *, should_raise: bool = False):
        self.should_raise = should_raise

    async def execute(self, _command):
        if self.should_raise:
            from app.modules.imports.errors import SourceArtifactNotFoundError

            raise SourceArtifactNotFoundError("artifact is missing")
        return SimpleNamespace(
            canonical_snapshot_id=uuid4(),
            trace_records_written=2,
        )


class _UploadUseCase:
    async def execute(self, _command):
        now = datetime.now(UTC)
        snapshot_id = uuid4()
        source_id = uuid4()
        return SimpleNamespace(
            upload=SimpleNamespace(
                id=uuid4(),
                source_id=source_id,
                file_name="asa.cfg",
                uploaded_by="qa",
                artifact_hash="abc123",
                size_bytes=11,
                raw_mime_type="text/plain",
                resolved_snapshot_id=snapshot_id,
                status="pending",
                created_at=now,
                consumed_at=None,
            ),
            snapshot=SimpleNamespace(
                id=snapshot_id,
                source_id=source_id,
                artifact_hash="abc123",
                source_format="text/plain",
                is_latest=True,
                created_at=now,
            ),
        )


def _build_test_client():
    from app.modules.imports.cisco_asa.http import router as cisco_router
    from app.modules.imports.http import router as imports_http_router

    app = FastAPI()
    app.include_router(imports_http_router.imports_router)
    app.include_router(cisco_router.cisco_asa_router)
    return TestClient(app)


def test_create_import_source_status_201_for_new_source():
    from app.modules.imports.di.dependencies import create_import_source_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[create_import_source_uc] = (
        lambda: _CreateSourceUseCase(created=True)
    )

    response = app_client.post(
        "/imports/sources",
        json={
            "vendor_code": "cisco_asa",
            "name": "edge-fw",
            "description": "prod",
            "active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["created"] is True


def test_create_import_source_status_200_for_existing_source():
    from app.modules.imports.di.dependencies import create_import_source_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[create_import_source_uc] = (
        lambda: _CreateSourceUseCase(created=False)
    )

    response = app_client.post(
        "/imports/sources",
        json={
            "vendor_code": "cisco_asa",
            "name": "edge-fw",
            "description": "prod",
            "active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["created"] is False


def test_get_import_source_returns_404_when_source_absent():
    from app.modules.imports.di.dependencies import get_import_source_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[get_import_source_uc] = (
        lambda: _GetSourceUseCase(source=None)
    )

    response = app_client.get(f"/imports/sources/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Import source not found"}


def test_list_import_sources_returns_items_from_sources_router():
    from app.modules.imports.di.dependencies import list_import_sources_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[list_import_sources_uc] = (
        lambda: _ListSourcesUseCase()
    )

    response = app_client.get("/imports/sources")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["vendor_code"] == "cisco_asa"


def test_list_import_vendors_returns_items_from_vendors_router():
    from app.modules.imports.di.dependencies import list_import_vendors_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[list_import_vendors_uc] = (
        lambda: _ListVendorsUseCase()
    )

    response = app_client.get("/imports/vendors")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["code"] == "cisco_asa"


def test_upload_artifact_returns_upload_and_snapshot_payload():
    from app.modules.imports.di.dependencies import upload_artifact_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[upload_artifact_uc] = lambda: _UploadUseCase()

    response = app_client.post(
        f"/imports/sources/{uuid4()}/uploads",
        json={
            "file_name": "asa.cfg",
            "uploaded_by": "qa",
            "raw_text": "line1\\nline2",
            "raw_mime_type": "text/plain",
            "source_format": "text/plain",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert "upload" in payload
    assert "snapshot" in payload
    assert payload["upload"]["file_name"] == "asa.cfg"
    assert payload["snapshot"]["is_latest"] is True


def test_get_source_snapshot_raw_text_returns_404_when_artifact_absent():
    from app.modules.imports.di.dependencies import get_source_artifact_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[get_source_artifact_uc] = (
        lambda: _GetArtifactUseCase(should_raise=True)
    )

    response = app_client.get(f"/imports/source-snapshots/{uuid4()}/raw-text")

    assert response.status_code == 404
    assert response.json() == {"detail": "Source artifact not found for snapshot"}


def test_get_source_snapshot_raw_text_returns_payload_when_present():
    from app.modules.imports.di.dependencies import get_source_artifact_uc

    app_client = _build_test_client()
    app_client.app.dependency_overrides[get_source_artifact_uc] = (
        lambda: _GetArtifactUseCase(should_raise=False)
    )

    response = app_client.get(f"/imports/source-snapshots/{uuid4()}/raw-text")

    assert response.status_code == 200
    payload = response.json()
    assert payload["line_count"] == 2
    assert payload["size_bytes"] == 11


def test_cisco_mapping_returns_404_when_snapshot_artifact_absent():
    from app.modules.imports.cisco_asa.di.dependencies import (
        get_run_cisco_mapping_use_case,
    )

    app_client = _build_test_client()
    app_client.app.dependency_overrides[get_run_cisco_mapping_use_case] = (
        lambda: _MappingUseCase(should_raise=True)
    )

    response = app_client.post(
        f"/imports/cisco-asa/snapshots/{uuid4()}/map-to-canonical"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Source artifact not found for snapshot"}


def test_cisco_mapping_returns_200_with_canonical_snapshot_payload():
    from app.modules.imports.cisco_asa.di.dependencies import (
        get_run_cisco_mapping_use_case,
    )

    app_client = _build_test_client()
    app_client.app.dependency_overrides[get_run_cisco_mapping_use_case] = (
        lambda: _MappingUseCase(should_raise=False)
    )

    response = app_client.post(
        f"/imports/cisco-asa/snapshots/{uuid4()}/map-to-canonical"
    )

    assert response.status_code == 200
    payload = response.json()
    assert "canonical_snapshot_id" in payload
