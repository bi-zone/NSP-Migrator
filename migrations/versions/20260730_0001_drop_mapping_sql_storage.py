"""drop mapping sql storage

Revision ID: 20260730_0001
Revises: 20260728_0001
Create Date: 2026-07-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0001"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "execute_plan_rule_mapping_scope_rule_id_fkey",
        "execute_plan_rule",
        type_="foreignkey",
    )
    op.drop_constraint(
        "execute_plan_mapping_scope_id_fkey",
        "execute_plan",
        type_="foreignkey",
    )

    op.drop_table("mapping_scope_rule_operand")
    op.drop_table("mapping_entity_candidate")
    op.drop_table("mapping_scope_rule")
    op.drop_table("mapping_entity_result")
    op.drop_index(op.f("ix_mapping_scope_csp_profile_id"), table_name="mapping_scope")
    op.drop_table("mapping_scope")


def downgrade() -> None:
    op.create_table(
        "mapping_scope",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("canonical_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("sdwan_target_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("csp_profile_id", sa.UUID(), nullable=False),
        sa.Column("vpc_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_snapshot_id"], ["canonical_snapshot.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["csp_profile_id"], ["csp_profile.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mapping_scope_csp_profile_id"),
        "mapping_scope",
        ["csp_profile_id"],
        unique=False,
    )

    op.create_table(
        "mapping_entity_result",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("mapping_scope_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_zone_id", sa.UUID(), nullable=True),
        sa.Column("canonical_object_id", sa.UUID(), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("selection_method", sa.String(length=64), nullable=True),
        sa.Column("selected_sdwan_entity_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["canonical_object_id"], ["canonical_object.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["canonical_zone_id"], ["canonical_zone.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mapping_scope_id"], ["mapping_scope.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mapping_scope_rule",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("mapping_scope_id", sa.UUID(), nullable=False),
        sa.Column("canonical_rule_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_rule_id"], ["canonical_rule.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mapping_scope_id"], ["mapping_scope.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mapping_entity_candidate",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("result_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("sdwan_entity_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_id"], ["mapping_entity_result.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mapping_scope_rule_operand",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("mapping_scope_rule_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("mapping_entity_result_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mapping_entity_result_id"],
            ["mapping_entity_result.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_scope_rule_id"], ["mapping_scope_rule.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "execute_plan_mapping_scope_id_fkey",
        "execute_plan",
        "mapping_scope",
        ["mapping_scope_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "execute_plan_rule_mapping_scope_rule_id_fkey",
        "execute_plan_rule",
        "mapping_scope_rule",
        ["mapping_scope_rule_id"],
        ["id"],
        ondelete="CASCADE",
    )
