"""Add a persistent per-day stamina schedule to weekly plans."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_0011"
down_revision = "20260802_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weekly_plans",
        sa.Column("daily_plan", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weekly_plans", "daily_plan")
