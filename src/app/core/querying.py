from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar


class SortDirection(StrEnum):
    """Direction shared by sortable application queries."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class Pagination:
    """Normalized pagination values"""

    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be greater than or equal to 1")
        if self.offset < 0:
            raise ValueError("offset must be greater than or equal to 0")


SortFieldT = TypeVar("SortFieldT", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class Sorting(Generic[SortFieldT]):
    """A whitelisted sort field paired with a shared direction."""

    field: SortFieldT
    direction: SortDirection = SortDirection.ASC
