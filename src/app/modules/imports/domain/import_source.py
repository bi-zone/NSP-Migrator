from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class ImportSource:
    id: UUID
    vendor_code: str
    name: str
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        vendor_code: str,
        name: str,
        description: str | None = None,
        active: bool = True,
    ) -> ImportSource:
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            vendor_code=vendor_code,
            name=name,
            description=description,
            active=active,
            created_at=now,
            updated_at=now,
        )
