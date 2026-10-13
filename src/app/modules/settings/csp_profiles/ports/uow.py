from __future__ import annotations

from typing import Protocol

from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.settings.csp_profiles.ports.credential_store import (
    CredentialStorePort,
)
from app.modules.settings.csp_profiles.ports.profile_repository import (
    CSPProfileRepositoryPort,
)


class CSPProfilesUnitOfWorkPort(IAsyncUnitOfWork, Protocol):
    """Single transaction over profile metadata and encrypted credentials."""

    profiles: CSPProfileRepositoryPort
    credentials: CredentialStorePort
