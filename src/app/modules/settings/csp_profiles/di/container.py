from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.integrations.sdwan_csp_api.client_factory import SDWANClientFactory
from app.modules.settings.csp_profiles.adapters.connection_tester import (
    HttpxCSPProfileConnectionTester,
)
from app.modules.settings.csp_profiles.adapters.db.uow import CSPProfilesUnitOfWork
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
)
from app.modules.settings.csp_profiles.adapters.security.certificate_bundle_converter import (
    CryptographyCertificateBundleConverter,
)
from app.modules.settings.csp_profiles.adapters.security.pem_inspector import (
    PEMCertificateInspector,
)
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


class CSPProfilesModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()
    credentials_config: providers.Dependency = providers.Dependency()

    credential_codec = providers.Singleton(
        AESGCMCredentialCodec,
        config=credentials_config,
    )
    certificate_inspector = providers.Singleton(PEMCertificateInspector)
    certificate_converter = providers.Singleton(CryptographyCertificateBundleConverter)
    sdwan_client_factory = providers.Singleton(SDWANClientFactory)
    connection_tester = providers.Factory(
        HttpxCSPProfileConnectionTester,
        client_factory=sdwan_client_factory,
    )
    uow = providers.Factory(
        CSPProfilesUnitOfWork,
        session_factory=session_factory,
        codec=credential_codec,
    )

    create_profile_use_case = providers.Factory(
        CreateProfileUseCase,
        uow=uow,
        certificate_inspector=certificate_inspector,
        certificate_converter=certificate_converter,
    )
    list_profiles_use_case = providers.Factory(ListProfilesUseCase, uow=uow)
    get_profile_use_case = providers.Factory(GetProfileUseCase, uow=uow)
    update_profile_use_case = providers.Factory(
        UpdateProfileUseCase,
        uow=uow,
        certificate_inspector=certificate_inspector,
        certificate_converter=certificate_converter,
    )
    delete_profile_use_case = providers.Factory(
        DeleteProfileUseCase,
        uow=uow,
    )
    remove_profile_password_use_case = providers.Factory(
        RemoveProfilePasswordUseCase,
        uow=uow,
    )
    test_profile_connection_use_case = providers.Factory(
        TestProfileConnectionUseCase,
        uow=uow,
        connection_tester=connection_tester,
    )
    change_profile_active_status_use_case = providers.Factory(
        ChangeProfileActiveStatusUseCase,
        uow=uow,
    )
