from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.core.errors import DomainValidationError
from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceCommand,
    CreateImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_source_artifact import (
    GetSourceArtifactQuery,
    GetSourceArtifactUseCase,
)
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactCommand,
    UploadArtifactUseCase,
)
from app.modules.imports.domain.import_source import ImportSource
from app.modules.imports.domain.import_vendor import ImportVendor
from app.modules.imports.domain.source_artifact import SourceArtifact
from app.modules.imports.domain.source_snapshot import SourceSnapshot
from app.modules.imports.errors import SourceArtifactNotFoundError


class _FakeSourcesRepo:
    def __init__(self, *, existing=None):
        self.existing = existing
        self.saved: list[ImportSource] = []
        self.by_id = {}

    async def get_by_vendor_code_and_name(self, vendor_code: str, name: str):
        if self.existing and (
            self.existing.vendor_code == vendor_code and self.existing.name == name
        ):
            return self.existing
        return None

    async def save(self, source: ImportSource):
        self.saved.append(source)
        self.by_id[source.id] = source

    async def get_by_id(self, source_id):
        return self.by_id.get(source_id)


class _FakeVendorsRepo:
    def __init__(self, vendor):
        self.vendor = vendor

    async def get_by_code(self, _code: str):
        return self.vendor


class _FakeSnapshotsRepo:
    def __init__(self, *, existing_snapshot=None):
        self.existing_snapshot = existing_snapshot
        self.saved: list[SourceSnapshot] = []
        self.mark_calls = 0

    async def get_by_hash(self, _source_id, artifact_hash: str):
        if (
            self.existing_snapshot
            and self.existing_snapshot.artifact_hash == artifact_hash
        ):
            return self.existing_snapshot
        return None

    async def mark_previous_not_latest(self, _source_id):
        self.mark_calls += 1

    async def save(self, snapshot: SourceSnapshot):
        self.saved.append(snapshot)


class _FakeArtifactsRepo:
    def __init__(self, *, artifact=None):
        self.artifact = artifact
        self.saved: list[SourceArtifact] = []

    async def get_by_snapshot_id(self, _snapshot_id):
        return self.artifact

    async def save(self, artifact: SourceArtifact):
        self.saved.append(artifact)


class _FakeUploadsRepo:
    def __init__(self):
        self.saved = []

    async def save(self, upload):
        self.saved.append(upload)


class _FakeUow:
    def __init__(
        self,
        *,
        vendors,
        sources,
        snapshots,
        artifacts,
        uploads,
    ):
        self.session = None
        self.vendors = vendors
        self.sources = sources
        self.snapshots = snapshots
        self.artifacts = artifacts
        self.uploads = uploads
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.commits += 1

    def __call__(self, reuse_session: bool = False):
        return self


def _active_vendor() -> ImportVendor:
    now = datetime.now(UTC)
    return ImportVendor(
        code="cisco_asa",
        display_name="Cisco ASA",
        active=True,
        created_at=now,
        updated_at=now,
    )


def test_create_import_source_rejects_unknown_or_inactive_vendor():
    source_repo = _FakeSourcesRepo()
    uow = _FakeUow(
        vendors=_FakeVendorsRepo(vendor=None),
        sources=source_repo,
        snapshots=_FakeSnapshotsRepo(),
        artifacts=_FakeArtifactsRepo(),
        uploads=_FakeUploadsRepo(),
    )
    use_case = CreateImportSourceUseCase(uow)

    try:
        asyncio.run(
            use_case.execute(
                CreateImportSourceCommand(
                    vendor_code="unknown",
                    name="edge-fw",
                )
            )
        )
        assert False, "expected DomainValidationError"
    except DomainValidationError:
        pass

    assert not source_repo.saved
    assert uow.commits == 0


def test_upload_artifact_reuses_existing_snapshot_without_creating_new_one():
    source_id = uuid4()
    existing_snapshot = SourceSnapshot.create(
        source_id=source_id,
        artifact_hash="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        source_format="text/plain",
    )
    snapshots = _FakeSnapshotsRepo(existing_snapshot=existing_snapshot)
    uploads = _FakeUploadsRepo()
    artifacts = _FakeArtifactsRepo()
    uow = _FakeUow(
        vendors=_FakeVendorsRepo(vendor=_active_vendor()),
        sources=_FakeSourcesRepo(),
        snapshots=snapshots,
        artifacts=artifacts,
        uploads=uploads,
    )
    use_case = UploadArtifactUseCase(uow)

    result = asyncio.run(
        use_case.execute(
            UploadArtifactCommand(
                source_id=source_id,
                file_name="asa.cfg",
                uploaded_by="qa",
                raw_text="abc",
            )
        )
    )

    assert result.snapshot.id == existing_snapshot.id
    assert snapshots.mark_calls == 0
    assert not snapshots.saved
    assert not artifacts.saved
    assert len(uploads.saved) == 1


def test_upload_artifact_creates_snapshot_and_artifact_for_new_hash():
    source_id = uuid4()
    snapshots = _FakeSnapshotsRepo(existing_snapshot=None)
    uploads = _FakeUploadsRepo()
    artifacts = _FakeArtifactsRepo()
    uow = _FakeUow(
        vendors=_FakeVendorsRepo(vendor=_active_vendor()),
        sources=_FakeSourcesRepo(),
        snapshots=snapshots,
        artifacts=artifacts,
        uploads=uploads,
    )
    use_case = UploadArtifactUseCase(uow)

    result = asyncio.run(
        use_case.execute(
            UploadArtifactCommand(
                source_id=source_id,
                file_name="asa.cfg",
                uploaded_by="qa",
                raw_text="line1\nline2",
                source_format="text/plain",
            )
        )
    )

    assert result.snapshot.source_id == source_id
    assert snapshots.mark_calls == 1
    assert len(snapshots.saved) == 1
    assert len(artifacts.saved) == 1
    assert len(uploads.saved) == 1


def test_get_source_artifact_raises_not_found_when_missing():
    uow = _FakeUow(
        vendors=_FakeVendorsRepo(vendor=_active_vendor()),
        sources=_FakeSourcesRepo(),
        snapshots=_FakeSnapshotsRepo(),
        artifacts=_FakeArtifactsRepo(artifact=None),
        uploads=_FakeUploadsRepo(),
    )
    use_case = GetSourceArtifactUseCase(uow)

    try:
        asyncio.run(
            use_case.execute(GetSourceArtifactQuery(source_snapshot_id=uuid4()))
        )
        assert False, "expected SourceArtifactNotFoundError"
    except SourceArtifactNotFoundError:
        pass


def test_get_source_artifact_returns_payload_when_present():
    snapshot_id = uuid4()
    artifact = SimpleNamespace(
        snapshot_id=snapshot_id,
        raw_text="line1\nline2",
        line_count=2,
        size_bytes=11,
    )
    uow = _FakeUow(
        vendors=_FakeVendorsRepo(vendor=_active_vendor()),
        sources=_FakeSourcesRepo(),
        snapshots=_FakeSnapshotsRepo(),
        artifacts=_FakeArtifactsRepo(artifact=artifact),
        uploads=_FakeUploadsRepo(),
    )
    use_case = GetSourceArtifactUseCase(uow)

    result = asyncio.run(
        use_case.execute(GetSourceArtifactQuery(source_snapshot_id=snapshot_id))
    )

    assert result.source_snapshot_id == snapshot_id
    assert result.line_count == 2
    assert result.size_bytes == 11
