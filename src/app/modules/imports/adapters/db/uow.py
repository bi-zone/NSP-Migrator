from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.imports.adapters.db.import_source_repository import (
    SQLAlchemyImportSourceRepository,
)
from app.modules.imports.adapters.db.import_upload_repository import (
    SQLAlchemyImportUploadRepository,
)
from app.modules.imports.adapters.db.import_vendor_repository import (
    SQLAlchemyImportVendorRepository,
)
from app.modules.imports.adapters.db.source_artifact_repository import (
    SQLAlchemySourceArtifactRepository,
)
from app.modules.imports.adapters.db.source_snapshot_repository import (
    SQLAlchemySourceSnapshotRepository,
)
from app.modules.imports.ports.uow import ImportsUoWPort


class ImportsUoW(SQLAlchemyUnitOfWork, ImportsUoWPort):
    async def __aenter__(self):
        await super().__aenter__()
        self.vendors = SQLAlchemyImportVendorRepository(self.session)
        self.sources = SQLAlchemyImportSourceRepository(self.session)
        self.uploads = SQLAlchemyImportUploadRepository(self.session)
        self.snapshots = SQLAlchemySourceSnapshotRepository(self.session)
        self.artifacts = SQLAlchemySourceArtifactRepository(self.session)
        return self
