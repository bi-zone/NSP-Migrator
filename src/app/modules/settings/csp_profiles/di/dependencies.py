from fastapi import Depends, Request

from app.di.dependencies import get_di_container
from app.modules.settings.csp_profiles.application.change_profile_active_status import (
    ChangeProfileActiveStatusUseCase,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.get_profile import (
    GetProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UpdateProfileUseCase,
)
from app.modules.settings.csp_profiles.di.container import (
    CSPProfilesModuleContainer,
)


def get_csp_profiles_container(request: Request) -> CSPProfilesModuleContainer:
    return get_di_container(request).settings_module().csp_profiles()


def create_profile_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> CreateProfileUseCase:
    return container.create_profile_use_case()


def list_profiles_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> ListProfilesUseCase:
    return container.list_profiles_use_case()


def get_profile_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> GetProfileUseCase:
    return container.get_profile_use_case()


def update_profile_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> UpdateProfileUseCase:
    return container.update_profile_use_case()


def delete_profile_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> DeleteProfileUseCase:
    return container.delete_profile_use_case()


def remove_profile_password_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> RemoveProfilePasswordUseCase:
    return container.remove_profile_password_use_case()


def test_profile_connection_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> TestProfileConnectionUseCase:
    return container.test_profile_connection_use_case()


def change_profile_active_status_uc(
    container: CSPProfilesModuleContainer = Depends(get_csp_profiles_container),
) -> ChangeProfileActiveStatusUseCase:
    return container.change_profile_active_status_use_case()
