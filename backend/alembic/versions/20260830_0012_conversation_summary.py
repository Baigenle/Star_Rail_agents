"""Add conversation summary and digest tracking for long-context support."""

from alembic import op
import sqlalchemy as sa


revision = "20260830_0012"
down_revision = "20260803_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("summary_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("summary_until", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "summary_until")
    op.drop_column("conversations", "summary_text")
