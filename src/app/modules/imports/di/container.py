from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.imports.adapters.db.uow import ImportsUoW
from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_import_source import (
    GetImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_import_sources import (
    GetImportSourcesUseCase,
)
from app.modules.imports.application.use_cases.get_import_vendors import (
    GetImportVendorsUseCase,
)
from app.modules.imports.application.use_cases.get_source_artifact import (
    GetSourceArtifactUseCase,
)
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsUseCase,
)
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactUseCase,
)


class ImportsModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()

    uow = providers.Factory(
        ImportsUoW,
        session_factory=session_factory,
    )

    create_import_source_use_case = providers.Factory(
        CreateImportSourceUseCase,
        uow=uow,
    )
    get_import_sources_use_case = providers.Factory(
        GetImportSourcesUseCase,
        uow=uow,
    )
    get_import_vendors_use_case = providers.Factory(
        GetImportVendorsUseCase,
        uow=uow,
    )
    get_source_snapshots_use_case = providers.Factory(
        GetSourceSnapshotsUseCase,
        uow=uow,
    )
    get_import_source_use_case = providers.Factory(
        GetImportSourceUseCase,
        uow=uow,
    )
    upload_artifact_use_case = providers.Factory(
        UploadArtifactUseCase,
        uow=uow,
    )
    get_source_artifact_use_case = providers.Factory(
        GetSourceArtifactUseCase,
        uow=uow,
    )
