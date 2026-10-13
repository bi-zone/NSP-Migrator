from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.settings.csp_profiles.di.container import (
    CSPProfilesModuleContainer,
)


class SettingsModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()
    credentials_config: providers.Dependency = providers.Dependency()

    csp_profiles = providers.Container(
        CSPProfilesModuleContainer,
        session_factory=session_factory,
        credentials_config=credentials_config,
    )
