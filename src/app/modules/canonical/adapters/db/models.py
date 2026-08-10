from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base, UUIDPrimaryKeyMixin


class CanonicalSnapshotModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id",
            "normalizer_code",
            "normalizer_version",
            name="uq_canonical_snapshot_source_normalizer",
        ),
    )

    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_snapshot.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    normalizer_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    zones_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    objects_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CanonicalIssueModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_issue"

    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CanonicalZoneModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_zone"

    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    zone_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CanonicalObjectModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_object"

    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    object_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    ip_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cidr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    range_start: Mapped[str | None] = mapped_column(INET, nullable=True)
    range_end: Mapped[str | None] = mapped_column(INET, nullable=True)
    fqdn: Mapped[str | None] = mapped_column(String(255), nullable=True)

    protocol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    port_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icmp_type: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    icmp_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CanonicalObjectMemberModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_object_member"

    parent_object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_object.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_object.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CanonicalRuleModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_rule"

    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CanonicalRuleOperandModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "canonical_rule_operand"
    __table_args__ = (
        CheckConstraint(
            "((target_zone_id IS NOT NULL)::int + (target_object_id IS NOT NULL)::int) = 1",
            name="ck_canonical_rule_operand_single_target",
        ),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_rule.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operand_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("canonical_zone.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("canonical_object.id", ondelete="RESTRICT"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
