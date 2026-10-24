"""Add retry scheduling for outbox delivery."""

import sqlalchemy as sa
from alembic import op

revision: str = "8f6c3a9b14d2"
down_revision: str | None = "f3d69a58c214"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_message",
        sa.Column(
            "delivery_attempts", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "outbox_message",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbox_message", "next_attempt_at")
    op.drop_column("outbox_message", "delivery_attempts")
