"""Add memory layers: player profiles (L0/L1), L1.5 facts, L2 episodic memories."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260905_0013"
down_revision = "20260830_0012"
branch_labels = None
depends_on = None

JSON_GENERIC = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "player_profiles",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("l0", JSON_GENERIC, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("l1", JSON_GENERIC, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "l15_facts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("fact_key", sa.String(length=64), nullable=False),
        sa.Column("fact_value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "fact_key", name="uq_l15_facts_user_key"),
    )
    op.create_table(
        "l2_memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trigger_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", JSON_GENERIC, nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_l2_memories_status", "l2_memories", ["status"])


def downgrade() -> None:
    op.drop_index("ix_l2_memories_status", table_name="l2_memories")
    op.drop_table("l2_memories")
    op.drop_table("l15_facts")
    op.drop_table("player_profiles")
