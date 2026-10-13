from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.querying import Pagination


class PaginationQuery(BaseModel):
    """Transport model for pagination without endpoint-specific upper bounds."""

    limit: Annotated[
        int | None,
        Field(
            ge=1,
            description="Page size",
        ),
    ] = None
    offset: Annotated[
        int,
        Field(
            ge=0,
            description="Row offset",
        ),
    ] = 0

    def to_pagination(self) -> Pagination:
        """Normalize HTTP values into the framework-independent query object."""
        return Pagination(limit=self.limit, offset=self.offset)


class PaginationResponse(BaseModel):
    """Pagination metadata for rule list and rule_scope responses."""

    limit: int | None = Field(
        default=None,
        description="Requested page size; null means return all matching rules.",
    )
    offset: int | None = Field(
        default=None,
        description="Requested row offset; null treated as zero by the use case.",
    )
    total: int = Field(
        description="Total rules matching filters before pagination slice."
    )

    # TODO: extract shared model_config into a BaseResponseSchema if more models need it.
    model_config = ConfigDict(from_attributes=True)
