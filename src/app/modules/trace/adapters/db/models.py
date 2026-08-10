from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base, UUIDPrimaryKeyMixin


class TraceRawToCanonicalModel(Base, UUIDPrimaryKeyMixin):
    """Persistence model for lineage rows produced by the raw -> canonical stage.

    Polymorphic ``canonical_id`` (no DB-level FK); referential integrity is
    enforced by CASCADE from ``source_snapshot`` and ``canonical_snapshot``.
    """

    __tablename__ = "trace_raw_to_canonical"

    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)

    source_line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)

    canonical_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    canonical_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source_line_start >= 1 AND source_line_end >= source_line_start",
            name="ck_trace_r2c_line_range",
        ),
        Index(
            "ix_trace_r2c_canonical_snapshot",
            "canonical_snapshot_id",
            "canonical_kind",
        ),
        Index(
            "ix_trace_r2c_source_snapshot_line",
            "source_snapshot_id",
            "source_line_start",
        ),
        Index(
            "ix_trace_r2c_target",
            "canonical_kind",
            "canonical_id",
        ),
        Index("ix_trace_r2c_created_at", "created_at"),
    )
