import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, UUIDPrimaryKeyMixin


class ReportModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "report"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    csp_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("csp_profile.id", ondelete="RESTRICT"),
        nullable=False,
    )
    commit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    vpc_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)


class ReportRuleModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "report_rule"

    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    src_zone_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dst_zone_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    src_addr_values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dst_addr_values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    service_values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    migration_result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
