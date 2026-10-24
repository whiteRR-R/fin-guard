"""Add used refresh token history and outbox messages."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3d69a58c214"
down_revision: str | None = "e2a71f5b0c38"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "used_refresh_token",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=500), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        sa.PrimaryKeyConstraint("session_id", "token_hash"),
    )

    op.create_table(
        "outbox_message",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("message_type", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_outbox_message_version_positive"),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_outbox_message_pending_created_at",
        "outbox_message",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_message_pending_created_at", table_name="outbox_message")
    op.drop_table("outbox_message")
    op.drop_table("used_refresh_token")
