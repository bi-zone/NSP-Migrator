from fastapi import Depends, Request

from app.di.dependencies import get_di_container
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
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactUseCase,
)
from app.modules.imports.di.container import ImportsModuleContainer


def get_imports_module_container(request: Request) -> ImportsModuleContainer:
    return get_di_container(request).imports_module()


def create_import_source_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> CreateImportSourceUseCase:
    return container.create_import_source_use_case()


def list_import_sources_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> GetImportSourcesUseCase:
    return container.get_import_sources_use_case()


def list_import_vendors_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> GetImportVendorsUseCase:
    return container.get_import_vendors_use_case()


def get_import_source_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> GetImportSourceUseCase:
    return container.get_import_source_use_case()


def upload_artifact_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> UploadArtifactUseCase:
    return container.upload_artifact_use_case()


def get_source_artifact_uc(
    container: ImportsModuleContainer = Depends(get_imports_module_container),
) -> GetSourceArtifactUseCase:
    return container.get_source_artifact_use_case()
