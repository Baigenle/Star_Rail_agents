"""Add weekly stamina plans."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260726_0005"
down_revision = "20260726_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("stamina_budget", sa.Integer(), nullable=False),
        sa.Column("allocated_stamina", sa.Integer(), nullable=False),
        sa.Column("weekly_runs_remaining", sa.Integer(), nullable=False),
        sa.Column("tasks", postgresql.JSONB(), nullable=False),
        sa.Column("notice", sa.String(300), nullable=False),
        sa.Column("evidence_version", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "week_start"),
    )
    op.create_index("ix_weekly_plans_user_id", "weekly_plans", ["user_id"])
    op.create_index("ix_weekly_plans_week_start", "weekly_plans", ["week_start"])


def downgrade() -> None:
    op.drop_table("weekly_plans")
