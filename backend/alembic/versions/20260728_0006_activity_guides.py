"""Add activity community guide submissions."""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0006"
down_revision = "20260726_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_guides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("activity_id", sa.String(80), nullable=False),
        sa.Column(
            "author_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("player_stage", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "reviewer_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_activity_guides_activity_id", "activity_guides", ["activity_id"])
    op.create_index("ix_activity_guides_author_id", "activity_guides", ["author_id"])
    op.create_index("ix_activity_guides_status", "activity_guides", ["status"])


def downgrade() -> None:
    op.drop_table("activity_guides")
