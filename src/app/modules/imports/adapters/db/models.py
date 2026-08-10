from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ImportSourceModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "import_source"
    __table_args__ = (
        UniqueConstraint("vendor_code", "name", name="uq_import_source_vendor_name"),
    )

    vendor_code: Mapped[str] = mapped_column(
        ForeignKey("import_vendor.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ImportVendorModel(Base, TimestampMixin):
    __tablename__ = "import_vendor"

    code: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SourceSnapshotModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "source_snapshot"

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_source.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    artifact_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    source_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SourceArtifactModel(Base):
    __tablename__ = "source_artifact"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    line_count: Mapped[int] = mapped_column(nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImportUploadModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_upload"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_source.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
