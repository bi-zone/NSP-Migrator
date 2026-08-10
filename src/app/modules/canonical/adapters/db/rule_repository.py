from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.canonical.adapters.db import mappers, models
from app.modules.canonical.domain.rule import CanonicalRule, CanonicalRuleOperand
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleRepositoryPort,
)


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
        q = (
            self._build_filtered_query(
                canonical_snapshot_id=canonical_snapshot_id, filters=filters
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
    ) -> list[CanonicalRule]:
        """Filtered rule page for GetCanonicalRuleScopeUseCase and mapping."""
        q = self._build_filtered_query(
            canonical_snapshot_id=canonical_snapshot_id, filters=filters
        ).order_by(
            models.CanonicalRuleModel.priority.asc(),
            models.CanonicalRuleModel.id.asc(),
        )
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

    def _build_filtered_query(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
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

        if filters.name_contains:
            pattern = f"%{filters.name_contains}%"
            q = q.where(
                models.CanonicalRuleModel.name.ilike(pattern)
                | models.CanonicalRuleModel.rule_key.ilike(pattern)
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

        if filters.operand_object_ids:
            object_exists = (
                select(models.CanonicalRuleOperandModel.id)
                .where(
                    models.CanonicalRuleOperandModel.rule_id
                    == models.CanonicalRuleModel.id,
                    models.CanonicalRuleOperandModel.target_object_id.in_(
                        filters.operand_object_ids
                    ),
                )
                .exists()
            )
            q = q.where(object_exists)

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
