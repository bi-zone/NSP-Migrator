"""Unit-of-work port for imports bounded context orchestration."""

from __future__ import annotations

from typing import Protocol

from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.imports.ports.import_source_repository import (
    ImportSourceRepositoryPort,
)
from app.modules.imports.ports.import_upload_repository import (
    ImportUploadRepositoryPort,
)
from app.modules.imports.ports.import_vendor_repository import (
    ImportVendorRepositoryPort,
)
from app.modules.imports.ports.source_artifact_repository import (
    SourceArtifactRepositoryPort,
)
from app.modules.imports.ports.source_snapshot_repository import (
    SourceSnapshotRepositoryPort,
)


class ImportsUoWPort(IAsyncUnitOfWork, Protocol):
    """Transactional aggregate of imports repositories.

    Use cases depend on this protocol to coordinate source, snapshot, artifact,
    upload, and vendor persistence under one transaction boundary.
    """

    vendors: ImportVendorRepositoryPort
    sources: ImportSourceRepositoryPort
    uploads: ImportUploadRepositoryPort
    snapshots: SourceSnapshotRepositoryPort
    artifacts: SourceArtifactRepositoryPort
