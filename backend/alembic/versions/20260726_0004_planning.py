"""Add progression and daily plans."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260726_0004"
down_revision = "20260726_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "progression_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("material_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("recommendation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_progression_plans_user_id", "progression_plans", ["user_id"])
    op.create_index("ix_progression_plans_status", "progression_plans", ["status"])
    op.create_table(
        "daily_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("stamina_budget", sa.Integer(), nullable=False),
        sa.Column("weekly_runs_remaining", sa.Integer(), nullable=False),
        sa.Column("tasks", postgresql.JSONB(), nullable=False),
        sa.Column("activity_notice", sa.String(160), nullable=False),
        sa.Column("evidence_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "plan_date"),
    )
    op.create_index("ix_daily_plans_user_id", "daily_plans", ["user_id"])
    op.create_index("ix_daily_plans_plan_date", "daily_plans", ["plan_date"])


def downgrade() -> None:
    op.drop_table("daily_plans")
    op.drop_table("progression_plans")
