import uuid

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, WithCreatedAtMixin


class MappingScopeModel(Base, WithCreatedAtMixin):
    """
    Mapping scope aggregate root.

    Scope groups selected canonical rules and binds them to one SD-WAN target.

    Selected rules are stored in mapping_scope_rule.
    Mapping results are stored separately in mapping_entity_result.
    """

    __tablename__ = "mapping_scope"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    title: Mapped[str] = mapped_column(String(128), nullable=False)

    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_snapshot.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sdwan_target_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    rules: Mapped[list["MappingScopeRuleModel"]] = relationship(
        "MappingScopeRuleModel",
        back_populates="scope",
        cascade="all, delete-orphan",
    )

    results: Mapped[list["MappingEntityResultModel"]] = relationship(
        "MappingEntityResultModel",
        back_populates="scope",
        cascade="all, delete-orphan",
    )


class MappingScopeRuleModel(Base):
    """
    Canonical rule included into mapping scope.

    This table intentionally stores only rule reference.
    """

    __tablename__ = "mapping_scope_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    mapping_scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_scope.id", ondelete="CASCADE"),
        nullable=False,
    )

    canonical_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_rule.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    action: Mapped[str] = mapped_column(String(32), nullable=False)

    scope: Mapped[MappingScopeModel] = relationship(
        "MappingScopeModel",
        back_populates="rules",
    )

    operands: Mapped[list["MappingScopeRuleOperandModel"]] = relationship(
        "MappingScopeRuleOperandModel",
        back_populates="rule",
        cascade="all, delete-orphan",
    )


class MappingEntityResultModel(Base, WithCreatedAtMixin):
    """
    Mapping result for one canonical entity inside one scope.

    One table stores all mapping result types:
    - zone;
    - address object;
    - service object.

    entity_type defines which canonical reference is used:

    ZONE:
        canonical_zone_id is filled.
        canonical_object_id is null.

    ADDR / SERVICE:
        canonical_zone_id is null.
        canonical_object_id is filled.

    Presence of this row means that canonical entity was processed.
    """

    __tablename__ = "mapping_entity_result"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    mapping_scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_scope.id", ondelete="CASCADE"),
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    canonical_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_zone.id", ondelete="RESTRICT"),
        nullable=True,
    )

    canonical_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_object.id", ondelete="RESTRICT"),
        nullable=True,
    )

    result_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    selection_method: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    selected_sdwan_entity_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    scope: Mapped[MappingScopeModel] = relationship(
        "MappingScopeModel",
        back_populates="results",
    )

    candidates: Mapped[list["MappingEntityCandidateModel"]] = relationship(
        "MappingEntityCandidateModel",
        back_populates="result",
        cascade="all, delete-orphan",
    )


class MappingEntityCandidateModel(Base):
    """
    Candidate SD-WAN entity for one mapping result.

    Candidate does not have its own entity_type.
    Candidate type is inherited from MappingEntityResultModel.entity_type

    sdwan_entity_id means:
    - SD-WAN zone id for ZONE result;
    - SD-WAN address object id for ADDR result;
    - SD-WAN service id for SERVICE result.
    """

    __tablename__ = "mapping_entity_candidate"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_entity_result.id", ondelete="CASCADE"),
        nullable=False,
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    sdwan_entity_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    result: Mapped[MappingEntityResultModel] = relationship(
        "MappingEntityResultModel",
        back_populates="candidates",
    )


class MappingScopeRuleOperandModel(Base):
    """Link from rule to entity result as Operand"""

    __tablename__ = "mapping_scope_rule_operand"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    mapping_scope_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_scope_rule.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    mapping_entity_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_entity_result.id", ondelete="CASCADE"),
        nullable=False,
    )

    rule: Mapped[MappingScopeRuleModel] = relationship(
        "MappingScopeRuleModel",
        back_populates="operands",
    )

    mapping_entity_result: Mapped["MappingEntityResultModel"] = relationship(
        "MappingEntityResultModel",
    )
