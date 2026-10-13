from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.settings.csp_profiles.adapters.db.credential_store import (
    SQLAlchemyEncryptedCredentialStore,
)
from app.modules.settings.csp_profiles.adapters.db.profile_repository import (
    SQLAlchemyCSPProfileRepository,
)
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
)
from app.modules.settings.csp_profiles.ports.uow import (
    CSPProfilesUnitOfWorkPort,
)


class CSPProfilesUnitOfWork(SQLAlchemyUnitOfWork, CSPProfilesUnitOfWorkPort):
    """"""

    def __init__(self, session_factory, codec: AESGCMCredentialCodec) -> None:
        super().__init__(session_factory)
        self._codec = codec

    async def __aenter__(self):
        await super().__aenter__()
        if self.session is None:
            raise RuntimeError("CSPProfilesUnitOfWork session is not initialized")
        self.profiles = SQLAlchemyCSPProfileRepository(self.session)
        self.credentials = SQLAlchemyEncryptedCredentialStore(
            self.session,
            self._codec,
        )
        return self
