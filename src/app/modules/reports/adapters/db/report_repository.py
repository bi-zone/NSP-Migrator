from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import (
    Exists,
    Select,
    asc,
    delete,
    desc,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.querying import Pagination, SortDirection, Sorting
from app.modules.reports.adapters.db.mappers import (
    report_from_model,
    report_rule_from_model,
    report_rule_to_model,
    report_to_model,
)
from app.modules.reports.adapters.db.models import ReportModel, ReportRuleModel
from app.modules.reports.domain.entities import Report
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
    ReportHeadersPage,
    ReportRuleFilters,
    ReportRulesPage,
    ReportsRepositoryPort,
    default_report_header_sorting,
)

_SORT_COLUMNS = {
    ReportHeaderSortField.CREATED_AT: ReportModel.created_at,
}


class SQLAlchemyReportsRepository(ReportsRepositoryPort):
    """Persist complete reports and load their immutable historical snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_report(self, report: Report) -> Report:
        return await self.add(report)

    async def add(self, entity: Report) -> Report:
        if entity.rules is None:
            raise ValueError("a persisted report must contain rules")

        self.session.add(report_to_model(entity))
        self.session.add_all([report_rule_to_model(rule) for rule in entity.rules])
        await self.session.flush()
        return entity

    async def get_report_by_id(self, report_id: UUID) -> Report | None:
        return await self.get_by_id(report_id)

    async def get_list(self) -> Sequence[Report]:
        page = await self.list_report_headers(
            Pagination(),
            filters=ReportHeaderFilters(),
            sorting=default_report_header_sorting(),
        )
        return page.reports

    async def get_by_id(self, entity_id: UUID) -> Report | None:
        model: ReportModel | None = await self.session.get(ReportModel, entity_id)
        if model is None:
            return None

        rule_models = list(
            (
                await self.session.scalars(
                    select(ReportRuleModel)
                    .where(ReportRuleModel.report_id == entity_id)
                    .order_by(
                        ReportRuleModel.priority.asc(),
                        ReportRuleModel.id.asc(),
                    )
                )
            ).all()
        )
        return report_from_model(
            model,
            rules=tuple(report_rule_from_model(rule) for rule in rule_models),
        )

    async def delete_report_by_id(self, report_id: UUID) -> None:
        await self.delete_by_id(report_id)

    async def delete_by_id(self, entity_id: UUID) -> None:
        await self.session.execute(
            delete(ReportModel).where(ReportModel.id == entity_id)
        )
        await self.session.flush()

    async def list_report_headers(
        self,
        pagination: Pagination,
        *,
        filters: ReportHeaderFilters,
        sorting: Sorting[ReportHeaderSortField],
    ) -> ReportHeadersPage:
        total = int(
            await self.session.scalar(
                self._filtered_query(filters)
                .with_only_columns(func.count(ReportModel.id))
                .order_by(None)
            )
            or 0
        )
        stmt = self._filtered_query(filters).order_by(*self._order_by_clauses(sorting))
        if pagination.limit is not None:
            stmt = stmt.limit(pagination.limit)
        if pagination.offset:
            stmt = stmt.offset(pagination.offset)

        models = list((await self.session.scalars(stmt)).all())
        return ReportHeadersPage(
            reports=tuple(report_from_model(model) for model in models),
            total=total,
        )

    def _filtered_query(self, filters: ReportHeaderFilters) -> Select:
        """Build one report-header predicate set for count and page queries."""
        stmt = select(ReportModel)
        search_by_name = filters.normalized_search_by_name()
        if search_by_name is not None:
            stmt = stmt.where(
                ReportModel.title.ilike(
                    f"%{_escape_like(search_by_name)}%",
                    escape="\\",
                )
            )
        if filters.created_from is not None:
            stmt = stmt.where(
                ReportModel.created_at >= _start_of_utc_day(filters.created_from)
            )
        if filters.created_to is not None:
            _out_range_day = _start_of_utc_day(filters.created_to + timedelta(days=1))
            stmt = stmt.where(
                ReportModel.created_at < _out_range_day  # includes day "to"
            )
        if filters.csp_profile_id is not None:
            stmt = stmt.where(ReportModel.csp_profile_id == filters.csp_profile_id)
        if filters.vpc_id is not None:
            stmt = stmt.where(ReportModel.vpc_id == filters.vpc_id)
        if filters.target_ids:
            stmt = stmt.where(ReportModel.target_id.in_(filters.target_ids))
        return stmt

    async def list_report_rules(
        self,
        report_id: UUID,
        pagination: Pagination,
        *,
        filters: ReportRuleFilters,
    ) -> ReportRulesPage | None:
        # -- check report existing
        report_header_id: UUID | None = await self.session.scalar(
            select(ReportModel.id).where(ReportModel.id == report_id)
        )
        if report_header_id is None:
            return None
        # -- get total count
        total = int(
            await self.session.scalar(
                self._filtered_report_rules_query(report_id, filters).with_only_columns(
                    func.count(ReportRuleModel.id)
                )
            )
            or 0
        )
        # -- retrieve list with filters
        stmt = self._filtered_report_rules_query(report_id, filters).order_by(
            ReportRuleModel.priority.asc(),
            ReportRuleModel.id.asc(),
        )
        if pagination.limit is not None:
            stmt = stmt.limit(pagination.limit)
        if pagination.offset:
            stmt = stmt.offset(pagination.offset)

        models: list[ReportRuleModel] = list((await self.session.scalars(stmt)).all())
        return ReportRulesPage(
            rules=tuple(report_rule_from_model(model) for model in models),
            total=total,
        )

    def _filtered_report_rules_query(
        self,
        report_id: UUID,
        filters: ReportRuleFilters,
    ) -> Select:
        """Build one report-rule predicate set for count and page queries."""
        stmt = select(ReportRuleModel).where(ReportRuleModel.report_id == report_id)
        # -- search by name
        search_by_policy_name: str | None = filters.normalized_search_by_policy_name()
        if search_by_policy_name is not None:
            stmt = stmt.where(
                ReportRuleModel.policy_name.ilike(
                    f"%{_escape_like(search_by_policy_name)}%",
                    escape="\\",
                )
            )
        # -- search by zone/addr_obj/service value
        search_by_object_value: str | None = filters.normalized_search_by_object_value()
        if search_by_object_value is not None:
            stmt = stmt.where(
                or_(
                    _json_values_match(
                        ReportRuleModel.src_zone_names, search_by_object_value
                    ),
                    _json_values_match(
                        ReportRuleModel.dst_zone_names, search_by_object_value
                    ),
                    _json_values_match(
                        ReportRuleModel.src_addr_values, search_by_object_value
                    ),
                    _json_values_match(
                        ReportRuleModel.dst_addr_values, search_by_object_value
                    ),
                    _json_values_match(
                        ReportRuleModel.service_values, search_by_object_value
                    ),
                )
            )
        # -- filter by migration result status
        if filters.migration_results:
            stmt = stmt.where(
                ReportRuleModel.migration_result.in_(
                    tuple(result.value for result in filters.migration_results)
                )
            )
        return stmt

    def _order_by_clauses(
        self,
        sorting: Sorting[ReportHeaderSortField],
    ) -> tuple:
        """Order by creation date with a stable report-ID tie-breaker."""
        column = _SORT_COLUMNS[sorting.field]
        primary = (
            asc(column) if sorting.direction == SortDirection.ASC else desc(column)
        )
        return primary, ReportModel.id.asc()


def _start_of_utc_day(value: date) -> datetime:
    return datetime.combine(
        value, time.min, tzinfo=UTC
    )  # time.min - 00:00:00 - start of day


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _json_values_match(
    json_column: InstrumentedAttribute[list[str]],
    search: str,
) -> Exists:
    """Return a predicate matching any JSON-array value by a safe partial match.
    TODO: json_array_elements_text - is PostgreSQL-specific func!

    `json_array_elements_text(json_column).table_valued("value")` expands `["Alice", "Bob"]` into a
    one-column table with rows `Alice` and `Bob`, column name is `value`; `EXISTS` then checks whether
    any row contains `value` (e.g. `"li"` matches `"Alice"`).
    """
    values = func.json_array_elements_text(json_column).table_valued("value")
    return exists(
        select(1)
        .select_from(values)
        .where(values.c.value.ilike(f"%{_escape_like(search)}%", escape="\\"))
    )
