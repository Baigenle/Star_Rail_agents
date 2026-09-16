"""Add reversible community moderation audit log."""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0007"
down_revision = "20260728_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_type", sa.String(24), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "actor_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("content_type", "content_id", "action", "actor_id", "created_at"):
        op.create_index(
            f"ix_moderation_actions_{column}", "moderation_actions", [column]
        )


def downgrade() -> None:
    op.drop_table("moderation_actions")
