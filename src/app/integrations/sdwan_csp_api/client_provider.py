from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from app.integrations.sdwan_csp_api.client_factory import SDWANClientFactory
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileConnectionValidationError,
    CSPProfileNotFoundError,
    CSPProfileRequiredError,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


class SDWANClientProvider:
    """Create uncached profile/VPC-scoped clients"""

    def __init__(
        self,
        *,
        uow_factory: Callable[[], CSPProfilesUnitOfWorkPort],
        client_factory: SDWANClientFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._client_factory = client_factory
        self._active_clients: dict[int, ISDWANCspHttpClient] = {}
        self._active_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(
        self,
        profile_id: UUID,
        vpc_id: str | None,
    ) -> AsyncIterator[ISDWANCspHttpClient]:
        uow = self._uow_factory()
        async with uow:
            profile = await uow.profiles.get_by_id(profile_id)
            if profile is None:
                if not await uow.profiles.list_all():
                    raise CSPProfileRequiredError
                raise CSPProfileNotFoundError

            credentials = await uow.credentials.get_for_connection(profile_id)

        if credentials is None or not profile.is_connectable:
            raise CSPProfileConnectionValidationError

        client = self._client_factory.create(
            profile=profile,
            credentials=credentials,
            vpc_id=vpc_id,
        )
        client_key = id(client)
        registered = False
        try:
            async with self._active_lock:
                self._active_clients[client_key] = client
                registered = True
            yield client
        finally:
            if registered:
                await self._release(client_key)
            else:
                await client.aclose()

    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]:
        async with self.acquire(profile_id, None) as client:
            response = await client.login()
            return response.allowed_vpcs

    async def close_all(self) -> None:
        async with self._active_lock:
            clients = list(self._active_clients.values())
            self._active_clients.clear()
        if clients:
            await asyncio.gather(
                *(client.aclose() for client in clients),
                return_exceptions=True,
            )

    async def _release(self, client_key: int) -> None:
        async with self._active_lock:
            client = self._active_clients.pop(client_key, None)
        if client is not None:
            await client.aclose()
