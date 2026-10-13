"""Query parameter models for canonical rule list endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.fastapi.querying import PaginationQuery
from app.core.querying import SortDirection, Sorting
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesQuery,
)
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleSearchScope,
    CanonicalRuleSortField,
)


class CanonicalRulesPaginationQuery(PaginationQuery):
    """Pagination constraints specific to canonical rule lists."""

    limit: Annotated[
        int | None,
        Field(
            ge=1,
            le=200,
            description="Page size for rules; omit to return all matching rules.",
        ),
    ] = None


class CanonicalRulesSortingQuery(BaseModel):
    """Whitelisted sorting parameters for canonical rules."""

    sort_by: Annotated[
        CanonicalRuleSortField | None,
        Field(
            description=(
                "Sort column whitelist. Omit for default priority asc, id asc."
            ),
        ),
    ] = None
    sort_dir: Annotated[
        SortDirection,
        Field(description="Sort direction; only applied when sort_by is set."),
    ] = SortDirection.ASC

    def to_sorting(self) -> Sorting[CanonicalRuleSortField] | None:
        """Return no override when the client did not select a sort field."""
        if self.sort_by is None:
            return None
        return Sorting(field=self.sort_by, direction=self.sort_dir)


class CanonicalRulesFilterQuery(BaseModel):
    """HTTP names and validation for canonical rule filters."""

    rule_id: Annotated[
        list[UUID] | None,
        Field(description="Explicit rule IDs to include."),
    ] = None
    search: Annotated[
        str | None,
        Field(
            description=(
                "Case-insensitive LIKE. Scope controlled by search_scope "
                "(default all: rule fields + object/zone names)."
            ),
        ),
    ] = None
    search_scope: Annotated[
        CanonicalRuleSearchScope,
        Field(
            description=(
                "Search target: all | rules | objects | zones. "
                "objects also matches nested group members."
            ),
        ),
    ] = CanonicalRuleSearchScope.ALL
    action: Annotated[
        str | None,
        Field(description="Exact match on rule action (for example permit, deny)."),
    ] = None
    enabled: Annotated[
        bool | None,
        Field(description="Filter by rule enabled flag."),
    ] = None
    section: Annotated[
        str | None,
        Field(
            description=(
                "Exact match on ACL / policy block name from source "
                "(for example global_access)."
            ),
        ),
    ] = None
    operand_zone_id: Annotated[
        list[UUID] | None,
        Field(description="Rules referencing any of these zone IDs."),
    ] = None
    operand_object_id: Annotated[
        list[UUID] | None,
        Field(
            description=(
                "Rules referencing these object IDs directly or via ancestor "
                "groups that transitively contain them."
            ),
        ),
    ] = None

    @field_validator(
        "search",
        "action",
        "section",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: object) -> object:
        """Strip textual filters and treat blank values as omitted."""
        if not isinstance(value, str):
            return value
        return value.strip() or None

    def to_filters(self) -> CanonicalRuleFilters:
        """Map HTTP field names to the canonical repository contract."""
        return CanonicalRuleFilters(
            rule_ids=list(self.rule_id) if self.rule_id else None,
            search=self.search,
            search_scope=self.search_scope,
            action=self.action,
            enabled=self.enabled,
            section=self.section,
            operand_zone_ids=list(self.operand_zone_id or ()),
            operand_object_ids=list(self.operand_object_id or ()),
        )


class SnapshotRulesQueryParams(
    CanonicalRulesPaginationQuery,
    CanonicalRulesSortingQuery,
    CanonicalRulesFilterQuery,
):
    """Flat FastAPI query model composed from reusable concerns."""

    model_config = ConfigDict(extra="forbid")

    def to_application_query(
        self,
        *,
        canonical_snapshot_id: UUID,
    ) -> GetCanonicalRulesQuery:
        """Map transport parameters explicitly to the application query."""
        return GetCanonicalRulesQuery(
            canonical_snapshot_id=canonical_snapshot_id,
            filters=self.to_filters(),
            pagination=self.to_pagination(),
            sorting=self.to_sorting(),
        )
