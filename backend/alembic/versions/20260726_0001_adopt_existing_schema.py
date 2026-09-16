"""Adopt existing schema and add progression plus community creation tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "20260726_0001"
down_revision = None
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("username", sa.String(32), nullable=False),
            sa.Column("email", sa.String(254), nullable=False),
            sa.Column("display_name", sa.String(48), nullable=False),
            sa.Column("password_hash", sa.String(256), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_username", "users", ["username"])
        op.create_index("ix_users_email", "users", ["email"])
    if not _has_table("user_characters"):
        op.create_table(
            "user_characters",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("character_id", sa.String(16), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("eidolon", sa.Integer(), nullable=False),
            sa.Column("is_favorite", sa.Boolean(), nullable=False),
            sa.Column("is_built", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "character_id"),
        )
        op.create_index("ix_user_characters_user_id", "user_characters", ["user_id"])
        op.create_index("ix_user_characters_character_id", "user_characters", ["character_id"])
    if not _has_table("user_memories"):
        op.create_table(
            "user_memories",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("memory_type", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(24), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
        op.create_index("ix_user_memories_memory_type", "user_memories", ["memory_type"])
    if not _has_table("user_character_progress"):
        op.create_table(
            "user_character_progress",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("character_id", sa.String(16), nullable=False),
            sa.Column("current_level", sa.Integer(), nullable=False),
            sa.Column("target_level", sa.Integer(), nullable=False),
            sa.Column("eidolon", sa.Integer(), nullable=False),
            sa.Column("current_skills", _json_type(), nullable=False),
            sa.Column("target_skills", _json_type(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "character_id"),
        )
        op.create_index("ix_user_character_progress_user_id", "user_character_progress", ["user_id"])
        op.create_index("ix_user_character_progress_character_id", "user_character_progress", ["character_id"])
    if not _has_table("custom_characters"):
        op.create_table(
            "custom_characters",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(48), nullable=False),
            sa.Column("visibility", sa.String(16), nullable=False),
            sa.Column("current_draft_version_id", sa.String(36)),
            sa.Column("published_version_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_custom_characters_author_id", "custom_characters", ["author_id"])
        op.create_index("ix_custom_characters_visibility", "custom_characters", ["visibility"])
    if not _has_table("custom_character_versions"):
        op.create_table(
            "custom_character_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("character_id", sa.String(36), sa.ForeignKey("custom_characters.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("payload", _json_type(), nullable=False),
            sa.Column("review_reason", sa.Text()),
            sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("submitted_at", sa.DateTime(timezone=True)),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("character_id", "version_number"),
        )
        op.create_index("ix_custom_character_versions_character_id", "custom_character_versions", ["character_id"])
        op.create_index("ix_custom_character_versions_status", "custom_character_versions", ["status"])
    if not _has_table("custom_character_sessions"):
        op.create_table(
            "custom_character_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("character_id", sa.String(36), sa.ForeignKey("custom_characters.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("pending_fields", _json_type(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_custom_character_sessions_character_id", "custom_character_sessions", ["character_id"])
        op.create_index("ix_custom_character_sessions_author_id", "custom_character_sessions", ["author_id"])
    if not _has_table("custom_character_messages"):
        op.create_table(
            "custom_character_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("custom_character_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("stage", sa.Integer(), nullable=False),
            sa.Column("structured_data", _json_type(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_custom_character_messages_session_id", "custom_character_messages", ["session_id"])


def downgrade() -> None:
    for table in (
        "custom_character_messages",
        "custom_character_sessions",
        "custom_character_versions",
        "custom_characters",
        "user_character_progress",
    ):
        if _has_table(table):
            op.drop_table(table)
