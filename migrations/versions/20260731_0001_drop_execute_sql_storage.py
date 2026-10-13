"""drop execute sql storage

Revision ID: 20260731_0001
Revises: 20260730_0001
Create Date: 2026-07-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0001"
down_revision: str | None = "20260730_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("execute_plan_rule")
    op.drop_table("execute_plan")


def downgrade() -> None:
    op.create_table(
        "execute_plan",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("mapping_scope_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "execute_plan_rule",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("execute_plan_id", sa.UUID(), nullable=False),
        sa.Column("mapping_scope_rule_id", sa.UUID(), nullable=False),
        sa.Column(
            "draft_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("matched_sdwan_rule_id", sa.Integer(), nullable=True),
        sa.Column("match_status", sa.String(length=32), nullable=False),
        sa.Column("match_info", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execute_plan_id"],
            ["execute_plan.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
