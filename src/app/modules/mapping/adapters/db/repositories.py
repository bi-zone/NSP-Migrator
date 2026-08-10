from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.mapping.adapters.db.mappers import (
    MappingEntityResultMapper,
    MappingScopeMapper,
)
from app.modules.mapping.adapters.db.models import (
    MappingEntityResultModel,
    MappingScopeModel,
    MappingScopeRuleModel,
)
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingResultStatus,
)
from app.modules.mapping.ports.repositories import (
    MappingEntityResultRepositoryPort,
    MappingScopeRepositoryPort,
)


class SqlAlchemyMappingScopeRepository(
    SqlAlchemyRepository[MappingScopeModel, UUID], MappingScopeRepositoryPort
):
    """
    SQLAlchemy implementation of MappingScopeRepositoryPort.

    Works with two ORM models:
    - MappingScopeModel;
    - MappingScopeRuleModel (as relationship of MappingScopeModel).
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MappingScopeModel)
        self._mapper = MappingScopeMapper()

    async def add_scope(self, scope: MappingScope) -> MappingScope:
        scope_model = await self.add(self._mapper.to_model(scope))
        return self._mapper.to_domain(scope_model)

    async def get_scope_by_id(
        self,
        scope_id: UUID,
        *,
        with_rules: bool = False,
    ) -> MappingScope | None:
        stmt = select(self.model).where(MappingScopeModel.id == scope_id)

        if with_rules:
            stmt = stmt.options(
                selectinload(self.model.rules).selectinload(
                    MappingScopeRuleModel.operands
                )
            )

        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._mapper.to_domain(model)

    async def attach_rules(
        self,
        *,
        scope_id: UUID,
        rules: list[MappingScopeRule],
    ) -> None:

        for rule in rules:
            if rule.mapping_scope_id != scope_id:
                raise ValueError("MappingScopeRule belongs to another scope")

            self.session.add(self._mapper.rule_mapper.to_model(rule))

        await self.session.flush()

    async def add_rule_operand(
        self,
        *,
        scope_id: UUID,
        operand: MappingScopeRuleOperand,
    ) -> None:
        rule = await self.get_scope_by_id(scope_id=scope_id, with_rules=True)
        if rule is None:
            raise ValueError("Mapping scope not found")

        if not any(
            item.id == operand.mapping_scope_rule_id for item in (rule.rules or [])
        ):
            raise ValueError("MappingScopeRule does not belong to provided scope")

        self.session.add(self._mapper.rule_mapper.operand_mapper.to_model(operand))
        await self.session.flush()

    async def list_recent_scopes(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MappingScope]:
        stmt = (
            select(self.model)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)

        return [self._mapper.to_domain(model) for model in result.scalars().all()]


class SqlAlchemyMappingEntityResultRepository(
    SqlAlchemyRepository[MappingEntityResultModel, UUID],
    MappingEntityResultRepositoryPort,
):
    """
    SQLAlchemy implementation of MappingEntityResultRepositoryPort.

    Works with two ORM models:
    - MappingEntityResultModel;
    - MappingEntityCandidateModel.

    Candidate rows are saved through result aggregate.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MappingEntityResultModel)
        self._mapper = MappingEntityResultMapper()

    def _select_result_stmt(self, *, with_candidates: bool):
        stmt = select(self.model)

        if with_candidates:
            stmt = stmt.options(selectinload(self.model.candidates))

        return stmt

    async def add_results(self, results: list[MappingEntityResult]) -> None:
        """
        Insert mapping results without deleting existing rows.

        DB unique constraints protect against duplicates inside the same scope.
        """
        await self.add_bulk([self._mapper.to_model(item) for item in results])

    async def get_result_by_id(
        self,
        result_id: UUID,
        *,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        stmt = self._select_result_stmt(with_candidates=with_candidates).where(
            self.model.id == result_id,
        )

        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._mapper.to_domain(model)

    async def get_result_by_canonical_entity(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        """
        Find result by logical canonical entity id.

        The repository hides the DB detail that zones and objects are stored
        in different canonical tables.
        """
        stmt = self._select_result_stmt(with_candidates=with_candidates).where(
            self.model.mapping_scope_id == scope_id,
            self.model.entity_type == entity_type.value,
        )

        if entity_type == MappingEntityType.ZONE:
            stmt = stmt.where(
                self.model.canonical_zone_id == canonical_entity_id,
            )
        else:
            stmt = stmt.where(
                self.model.canonical_object_id == canonical_entity_id,
            )

        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._mapper.to_domain(model)

    async def list_by_scope(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType | None = None,
        status: MappingResultStatus | None = None,
        with_candidates: bool = False,
    ) -> list[MappingEntityResult]:
        stmt = self._select_result_stmt(with_candidates=with_candidates).where(
            self.model.mapping_scope_id == scope_id,
        )

        if entity_type is not None:
            stmt = stmt.where(
                self.model.entity_type == entity_type.value,
            )

        if status is not None:
            stmt = stmt.where(
                self.model.result_status == status.value,
            )

        stmt = stmt.order_by(
            self.model.entity_type.asc(),
            self.model.created_at.asc(),
        )

        result = await self.session.execute(stmt)

        return [self._mapper.to_domain(model) for model in result.scalars().all()]

    async def save_result(self, result: MappingEntityResult) -> MappingEntityResult:
        """
        Save one mapping result aggregate.

        Typical callers:
        - manual candidate selection;
        - direct SD-WAN object selection;
        - auto-created SD-WAN object selection.

        When result.candidates is None, mapper does not touch relationship.
        When result.candidates is a list, candidates are synced by merge.
        """
        saved_model = await self.save(self._mapper.to_model(result))
        return self._mapper.to_domain(saved_model)
