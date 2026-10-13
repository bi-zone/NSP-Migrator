from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.querying import SortDirection, Sorting
from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.canonical.adapters.db import mappers, models
from app.modules.canonical.domain.rule import CanonicalRule, CanonicalRuleOperand
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleRepositoryPort,
    CanonicalRuleSearchScope,
    CanonicalRuleSortField,
)

_SORT_COLUMNS = {
    CanonicalRuleSortField.PRIORITY: models.CanonicalRuleModel.priority,
    CanonicalRuleSortField.NAME: models.CanonicalRuleModel.name,
    CanonicalRuleSortField.ACTION: models.CanonicalRuleModel.action,
    CanonicalRuleSortField.ENABLED: models.CanonicalRuleModel.enabled,
    CanonicalRuleSortField.SECTION: models.CanonicalRuleModel.section,
    CanonicalRuleSortField.RULE_KEY: models.CanonicalRuleModel.rule_key,
    CanonicalRuleSortField.DESCRIPTION: models.CanonicalRuleModel.description,
}


class SQLAlchemyCanonicalRuleRepository(
    SqlAlchemyRepository[models.CanonicalRuleModel, UUID],
    CanonicalRuleRepositoryPort,
):
    """Persist rules/operands and run filtered reads for rule_scope."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.CanonicalRuleModel)

    async def bulk_save(self, rules: list[CanonicalRule]) -> None:
        """Insert rule rows during SaveCanonicalSnapshotUseCase write path."""
        if not rules:
            return
        self.session.add_all([mappers.rule_to_model(r) for r in rules])
        await self.session.flush()

    async def bulk_save_operands(self, operands: list[CanonicalRuleOperand]) -> None:
        """Insert operand rows after rules (FK to rule_id)."""
        if not operands:
            return
        self.session.add_all([mappers.operand_to_model(o) for o in operands])
        await self.session.flush()

    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, rule_id: UUID
    ) -> CanonicalRule | None:
        """Single rule lookup scoped to snapshot; used by rule detail use case."""
        q = select(models.CanonicalRuleModel).where(
            models.CanonicalRuleModel.id == rule_id,
            models.CanonicalRuleModel.canonical_snapshot_id == canonical_snapshot_id,
        )
        model = (await self.session.scalars(q)).first()
        return mappers.rule_to_entity(model) if model else None

    async def get_by_snapshot(self, canonical_snapshot_id: UUID) -> list[CanonicalRule]:
        """All rules for snapshot ordered by priority."""
        q = (
            select(models.CanonicalRuleModel)
            .where(
                models.CanonicalRuleModel.canonical_snapshot_id == canonical_snapshot_id
            )
            .order_by(models.CanonicalRuleModel.priority.asc())
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.rule_to_entity(m) for m in rows]

    async def get_operands_by_rule(
        self, *, canonical_snapshot_id: UUID, rule_id: UUID
    ) -> list[CanonicalRuleOperand]:
        """Operands for one rule; used by hydrated rule detail."""
        q = (
            select(models.CanonicalRuleOperandModel)
            .join(
                models.CanonicalRuleModel,
                models.CanonicalRuleModel.id
                == models.CanonicalRuleOperandModel.rule_id,
            )
            .where(
                models.CanonicalRuleModel.canonical_snapshot_id
                == canonical_snapshot_id,
                models.CanonicalRuleOperandModel.rule_id == rule_id,
            )
            .order_by(
                models.CanonicalRuleOperandModel.operand_role.asc(),
                models.CanonicalRuleOperandModel.position.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.operand_to_entity(m) for m in rows]

    async def get_operands_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalRuleOperand]:
        """All operands in snapshot; used when loading full graph."""
        q = (
            select(models.CanonicalRuleOperandModel)
            .join(
                models.CanonicalRuleModel,
                models.CanonicalRuleModel.id
                == models.CanonicalRuleOperandModel.rule_id,
            )
            .where(
                models.CanonicalRuleModel.canonical_snapshot_id == canonical_snapshot_id
            )
            .order_by(
                models.CanonicalRuleOperandModel.rule_id.asc(),
                models.CanonicalRuleOperandModel.operand_role.asc(),
                models.CanonicalRuleOperandModel.position.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.operand_to_entity(m) for m in rows]

    async def count_filtered(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
    ) -> int:
        """Total rules matching filters; paired with list_filtered for pagination."""
        expanded_object_ids = await self._expand_operand_object_ids(
            canonical_snapshot_id=canonical_snapshot_id,
            object_ids=filters.operand_object_ids,
        )
        search_object_ids = await self._resolve_search_object_ids(
            canonical_snapshot_id=canonical_snapshot_id,
            filters=filters,
        )
        q = (
            self._build_filtered_query(
                canonical_snapshot_id=canonical_snapshot_id,
                filters=filters,
                expanded_object_ids=expanded_object_ids,
                search_object_ids=search_object_ids,
            )
            .with_only_columns(func.count(models.CanonicalRuleModel.id))
            .order_by(None)
        )
        result = await self.session.execute(q)
        return int(result.scalar_one())

    async def list_filtered(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
        limit: int | None,
        offset: int | None,
        sort: Sorting[CanonicalRuleSortField] | None = None,
    ) -> list[CanonicalRule]:
        """Filtered rule page for GetCanonicalRuleScopeUseCase and list API."""
        expanded_object_ids = await self._expand_operand_object_ids(
            canonical_snapshot_id=canonical_snapshot_id,
            object_ids=filters.operand_object_ids,
        )
        search_object_ids = await self._resolve_search_object_ids(
            canonical_snapshot_id=canonical_snapshot_id,
            filters=filters,
        )
        q = self._build_filtered_query(
            canonical_snapshot_id=canonical_snapshot_id,
            filters=filters,
            expanded_object_ids=expanded_object_ids,
            search_object_ids=search_object_ids,
        ).order_by(*self._order_by_clauses(sort))
        if limit is not None:
            q = q.limit(limit)
        if offset is not None:
            q = q.offset(offset)
        rows = list((await self.session.scalars(q)).all())
        return [mappers.rule_to_entity(m) for m in rows]

    async def get_operands_by_rule_ids(
        self, *, canonical_snapshot_id: UUID, rule_ids: list[UUID]
    ) -> list[CanonicalRuleOperand]:
        """Batch operand fetch for a filtered rules page in rule_scope."""
        if not rule_ids:
            return []
        q = (
            select(models.CanonicalRuleOperandModel)
            .join(
                models.CanonicalRuleModel,
                models.CanonicalRuleModel.id
                == models.CanonicalRuleOperandModel.rule_id,
            )
            .where(
                models.CanonicalRuleModel.canonical_snapshot_id
                == canonical_snapshot_id,
                models.CanonicalRuleOperandModel.rule_id.in_(rule_ids),
            )
            .order_by(
                models.CanonicalRuleOperandModel.rule_id.asc(),
                models.CanonicalRuleOperandModel.operand_role.asc(),
                models.CanonicalRuleOperandModel.position.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.operand_to_entity(m) for m in rows]

    async def _expand_operand_object_ids(
        self,
        *,
        canonical_snapshot_id: UUID,
        object_ids: list[UUID],
    ) -> list[UUID]:
        """Union seed object ids with ancestor group ids (membership walk up).

        Mirrors the reverse of group_expansion BFS: leaf/member -> parent groups,
        so filtering by a nested member also matches rules whose operand is the
        containing group.
        """
        if not object_ids:
            return []

        collected: set[UUID] = set(object_ids)
        pending: set[UUID] = set(object_ids)

        while pending:
            parent_q = (
                select(models.CanonicalObjectMemberModel.parent_object_id)
                .join(
                    models.CanonicalObjectModel,
                    models.CanonicalObjectModel.id
                    == models.CanonicalObjectMemberModel.parent_object_id,
                )
                .where(
                    models.CanonicalObjectModel.canonical_snapshot_id
                    == canonical_snapshot_id,
                    models.CanonicalObjectMemberModel.child_object_id.in_(
                        list(pending)
                    ),
                )
            )
            parents = set((await self.session.scalars(parent_q)).all())
            pending = parents - collected
            collected |= parents

        return list(collected)

    def _order_by_clauses(
        self, sort: Sorting[CanonicalRuleSortField] | None
    ) -> tuple:
        """Default priority asc, id asc; optional client sort with id tie-breaker."""
        if sort is None:
            return (
                models.CanonicalRuleModel.priority.asc(),
                models.CanonicalRuleModel.id.asc(),
            )

        column = _SORT_COLUMNS[sort.field]
        primary = (
            asc(column)
            if sort.direction == SortDirection.ASC
            else desc(column)
        )
        return (primary, models.CanonicalRuleModel.id.asc())

    async def _resolve_search_object_ids(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
    ) -> list[UUID] | None:
        """Object ids matching search text, plus ancestor groups.

        Returns ``None`` when object-side search is not needed for the scope.
        Returns ``[]`` when scope needs objects but nothing matched.
        """
        search = filters.normalized_search()
        if not search:
            return None
        if filters.search_scope not in (
            CanonicalRuleSearchScope.ALL,
            CanonicalRuleSearchScope.OBJECTS,
        ):
            return None

        pattern = f"%{search}%"
        object_q = select(models.CanonicalObjectModel.id).where(
            models.CanonicalObjectModel.canonical_snapshot_id == canonical_snapshot_id,
            or_(
                models.CanonicalObjectModel.name.ilike(pattern),
                models.CanonicalObjectModel.object_key.ilike(pattern),
                models.CanonicalObjectModel.cidr.ilike(pattern),
                models.CanonicalObjectModel.fqdn.ilike(pattern),
            ),
        )
        matched = list((await self.session.scalars(object_q)).all())
        if not matched:
            return []
        return await self._expand_operand_object_ids(
            canonical_snapshot_id=canonical_snapshot_id,
            object_ids=matched,
        )

    def _rule_fields_search_clause(self, pattern: str):
        return or_(
            models.CanonicalRuleModel.name.ilike(pattern),
            models.CanonicalRuleModel.rule_key.ilike(pattern),
            models.CanonicalRuleModel.section.ilike(pattern),
            models.CanonicalRuleModel.description.ilike(pattern),
            models.CanonicalRuleModel.action.ilike(pattern),
        )

    def _zone_search_exists(self, *, pattern: str):
        return (
            select(models.CanonicalRuleOperandModel.id)
            .join(
                models.CanonicalZoneModel,
                models.CanonicalZoneModel.id
                == models.CanonicalRuleOperandModel.target_zone_id,
            )
            .where(
                models.CanonicalRuleOperandModel.rule_id == models.CanonicalRuleModel.id,
                or_(
                    models.CanonicalZoneModel.name.ilike(pattern),
                    models.CanonicalZoneModel.zone_key.ilike(pattern),
                ),
            )
            .exists()
        )

    def _object_ids_exists(self, object_ids: list[UUID]):
        return (
            select(models.CanonicalRuleOperandModel.id)
            .where(
                models.CanonicalRuleOperandModel.rule_id == models.CanonicalRuleModel.id,
                models.CanonicalRuleOperandModel.target_object_id.in_(object_ids),
            )
            .exists()
        )

    def _apply_search_filter(
        self,
        q: Select,
        *,
        filters: CanonicalRuleFilters,
        search_object_ids: list[UUID] | None,
    ) -> Select:
        search = filters.normalized_search()
        if not search:
            return q

        pattern = f"%{search}%"
        scope = filters.search_scope
        clauses = []
        if scope in (CanonicalRuleSearchScope.ALL, CanonicalRuleSearchScope.RULES):
            clauses.append(self._rule_fields_search_clause(pattern))
        if scope in (CanonicalRuleSearchScope.ALL, CanonicalRuleSearchScope.ZONES):
            clauses.append(self._zone_search_exists(pattern=pattern))
        if (
            scope
            in (CanonicalRuleSearchScope.ALL, CanonicalRuleSearchScope.OBJECTS)
            and search_object_ids
        ):
            clauses.append(self._object_ids_exists(search_object_ids))

        if clauses:
            return q.where(or_(*clauses))
        # e.g. objects-only search with zero object hits
        return q.where(models.CanonicalRuleModel.id.is_(None))

    def _build_filtered_query(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
        expanded_object_ids: list[UUID] | None = None,
        search_object_ids: list[UUID] | None = None,
    ) -> Select:
        """Apply CanonicalRuleFilters to a base snapshot rules query.

        fw_applicable_only matches Cisco metadata stored in rule description
        (processing_status=fw_applicable|skipped_for_now). Must stay in sync with
        CanonicalRuleFilters port docstring.
        """
        q: Select = select(models.CanonicalRuleModel).where(
            models.CanonicalRuleModel.canonical_snapshot_id == canonical_snapshot_id
        )

        if filters.rule_ids:
            q = q.where(models.CanonicalRuleModel.id.in_(filters.rule_ids))

        q = self._apply_search_filter(
            q, filters=filters, search_object_ids=search_object_ids
        )

        if filters.action is not None:
            q = q.where(models.CanonicalRuleModel.action == filters.action)

        if filters.enabled is not None:
            q = q.where(models.CanonicalRuleModel.enabled.is_(filters.enabled))

        if filters.section is not None:
            q = q.where(models.CanonicalRuleModel.section == filters.section)

        if filters.operand_zone_ids:
            zone_exists = (
                select(models.CanonicalRuleOperandModel.id)
                .where(
                    models.CanonicalRuleOperandModel.rule_id
                    == models.CanonicalRuleModel.id,
                    models.CanonicalRuleOperandModel.target_zone_id.in_(
                        filters.operand_zone_ids
                    ),
                )
                .exists()
            )
            q = q.where(zone_exists)

        object_ids = (
            expanded_object_ids
            if expanded_object_ids is not None
            else filters.operand_object_ids
        )
        if object_ids:
            q = q.where(self._object_ids_exists(object_ids))

        if filters.fw_applicable_only is True:
            q = q.where(
                models.CanonicalRuleModel.description.ilike(
                    "%processing_status=fw_applicable%"
                )
            )
        elif filters.fw_applicable_only is False:
            q = q.where(
                models.CanonicalRuleModel.description.ilike(
                    "%processing_status=skipped_for_now%"
                )
            )

        return q
