"""Store the latest player self-review on each custom character version."""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0010"
down_revision = "20260729_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_character_versions",
        sa.Column("self_review", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_character_versions", "self_review")
