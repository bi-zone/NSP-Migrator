from typing import Protocol
from uuid import UUID

from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalRule,
    CanonicalScopeEntities,
    CanonicalService,
)


class CanonicalReaderPort(Protocol):

    async def get_canonical_scope_entities_data(
        self,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> CanonicalScopeEntities:
        """Get zones and objects (addr, services) from canonical"""
        ...

    async def get_canonical_addr_object(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalAddrObject | None: ...

    async def get_canonical_service(
        self, canonical_snapshot_id: UUID, canonical_object_id: UUID
    ) -> CanonicalService | None: ...

    async def get_canonical_scope_rules(
        self, canonical_snapshot_id: UUID, canonical_rules_ids: list[UUID]
    ) -> list[CanonicalRule]: ...
