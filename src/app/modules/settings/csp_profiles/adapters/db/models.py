from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CSPProfileModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "csp_profile"
    __table_args__ = (
        Index("uq_csp_profile_name_lower", text("lower(name)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CSPProfileCredentialsModel(Base):
    __tablename__ = "csp_profile_credentials"
    __table_args__ = (
        CheckConstraint(
            "format_version > 0",
            name="ck_csp_profile_credentials_format_version_positive",
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("csp_profile.id", ondelete="CASCADE"),
        primary_key=True,
    )
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    format_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    has_password: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_certificate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    certificate_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    certificate_not_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    certificate_has_private_key: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
