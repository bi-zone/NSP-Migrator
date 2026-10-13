from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
    StoredCredentialMetadata,
)


@dataclass(frozen=True, slots=True)
class CredentialWrite:
    """Plaintext write input."""

    credentials: ProfileCredentials = field(repr=False)
    metadata: StoredCredentialMetadata


class CredentialStorePort(Protocol):
    """Application-level storage contract hiding encryption and persistence."""

    @abstractmethod
    async def put_for_profile(
        self, profile_id: UUID, credential_write: CredentialWrite
    ) -> None: ...

    @abstractmethod
    async def get_for_connection(
        self, profile_id: UUID
    ) -> ProfileCredentials | None: ...

    @abstractmethod
    async def remove_password(self, profile_id: UUID) -> None: ...

    @abstractmethod
    async def delete_for_profile(self, profile_id: UUID) -> None: ...
