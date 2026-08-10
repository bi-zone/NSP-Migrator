import uuid

from sqlalchemy import UUID, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, WithCreatedAtMixin


class ExecutePlanModel(Base, WithCreatedAtMixin):
    __tablename__ = "execute_plan"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    mapping_scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_scope.id", ondelete="CASCADE"),
        nullable=False,
    )


class ExecutePlanRuleModel(Base):
    __tablename__ = "execute_plan_rule"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )

    execute_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execute_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    mapping_scope_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_scope_rule.id", ondelete="CASCADE"),
        nullable=False,
    )

    draft_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    matched_sdwan_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    match_info: Mapped[str] = mapped_column(Text, nullable=False)
