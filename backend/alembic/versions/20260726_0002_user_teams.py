"""Add saved official teams."""

from alembic import op
import sqlalchemy as sa


revision = "20260726_0002"
down_revision = "20260726_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_teams_user_id", "user_teams", ["user_id"])
    op.create_table(
        "user_team_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("user_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("character_id", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("team_id", "position"),
        sa.UniqueConstraint("team_id", "character_id"),
    )
    op.create_index("ix_user_team_members_team_id", "user_team_members", ["team_id"])
    op.create_index(
        "ix_user_team_members_character_id",
        "user_team_members",
        ["character_id"],
    )


def downgrade() -> None:
    op.drop_table("user_team_members")
    op.drop_table("user_teams")
