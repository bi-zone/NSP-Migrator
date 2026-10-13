from __future__ import annotations

from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from app.modules.settings.csp_profiles.domain.entities import CSPProfile


class CSPProfileRepositoryPort(Protocol):
    """Persistence contract for secret-free CSP profile metadata."""

    @abstractmethod
    async def save(self, profile: CSPProfile) -> None: ...

    @abstractmethod
    async def get_by_id(self, profile_id: UUID) -> CSPProfile | None: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> CSPProfile | None: ...

    @abstractmethod
    async def list_all(
        self,
        active_only: bool = False,
        profile_ids: tuple[UUID, ...] | None = None,
    ) -> list[CSPProfile]: ...

    @abstractmethod
    async def update(self, profile: CSPProfile) -> bool: ...

    @abstractmethod
    async def change_active_status(
        self, profile_id: UUID, new_status: bool
    ) -> bool: ...

    @abstractmethod
    async def delete(self, profile_id: UUID) -> bool: ...
