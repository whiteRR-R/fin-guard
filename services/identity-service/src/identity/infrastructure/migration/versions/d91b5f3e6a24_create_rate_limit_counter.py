import sqlalchemy as sa
from alembic import op

revision: str = "d91b5f3e6a24"
down_revision: str | None = "c4e8d2a7f913"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counter",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash", "window_start"),
    )
    op.create_index(
        "ix_rate_limit_counter_window_start",
        "rate_limit_counter",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counter_window_start", table_name="rate_limit_counter")
    op.drop_table("rate_limit_counter")
