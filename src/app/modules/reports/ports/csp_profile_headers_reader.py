from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CSPProfileHeaderDTO:
    """Presentation data for a CSP profile linked from a report header."""

    id: UUID
    name: str
    base_url: str


class CSPProfileHeadersReaderPort(Protocol):
    """Read CSP profile headers needed to present report headers."""

    async def get_header_by_id(self, profile_id: UUID) -> CSPProfileHeaderDTO:
        """Return one CSP profile header by its identifier."""
        ...

    async def get_headers_by_ids(
        self,
        profile_ids: tuple[UUID, ...],
    ) -> tuple[CSPProfileHeaderDTO, ...]:
        """Return a header for every requested profile ID."""
