"""Add persisted chat job progress and public execution events."""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0009"
down_revision = "20260728_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_jobs", sa.Column("partial_answer", sa.Text(), nullable=True))
    op.add_column(
        "chat_jobs",
        sa.Column("progress_payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "chat_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("chat_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("agent", sa.String(80), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "job_id",
            "sequence",
            name="uq_chat_job_events_job_sequence",
        ),
    )
    op.create_index("ix_chat_job_events_job_id", "chat_job_events", ["job_id"])
    op.create_index(
        "ix_chat_job_events_event_type",
        "chat_job_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_table("chat_job_events")
    op.drop_column("chat_jobs", "progress_payload")
    op.drop_column("chat_jobs", "partial_answer")
