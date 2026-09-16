"""Add worldbook activation states (per conversation persistence)."""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0015"
down_revision = "20260905_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worldbook_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("entry_id", sa.String(length=160), nullable=False),
        sa.Column("activation", sa.Float(), nullable=False, server_default="0"),
        sa.Column("user_silence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_silence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "conversation_id", "entry_id", name="uq_worldbook_states_conv_entry"
        ),
    )


def downgrade() -> None:
    op.drop_table("worldbook_states")
