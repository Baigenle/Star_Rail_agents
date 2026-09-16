"""Add care cue column to conversations (spec §9.6 relationship hint)."""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0014"
down_revision = "20260905_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("next_care_cue", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "next_care_cue")
