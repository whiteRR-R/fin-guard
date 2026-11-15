import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e8d2a7f913"
down_revision: str | None = "8f6c3a9b14d2"
branch_labels: str | None = None
depends_on: str | None = None


machine_scope_type = postgresql.ENUM(
    "transactions:write",
    "transactions:read",
    "risk-results:read",
    "webhooks:manage",
    name="machine_scope",
    create_type=False,
)
service_account_status_type = postgresql.ENUM(
    "ACTIVE",
    "REVOKED",
    name="service_account_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    machine_scope_type.create(bind)
    service_account_status_type.create(bind)

    op.create_table(
        "service_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(machine_scope_type), nullable=False),
        sa.Column("status", service_account_status_type, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cardinality(scopes) > 0", name="ck_service_account_scopes_nonempty"
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE') = (revoked_at IS NULL)",
            name="ck_service_account_revoked_at_matches_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )

    op.create_table(
        "service_account_secret",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_account_id", sa.Uuid(), nullable=False),
        sa.Column("secret_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_account_id"], ["service_account.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_hash"),
    )
    op.create_index(
        "ix_service_account_secret_service_account_id",
        "service_account_secret",
        ["service_account_id"],
    )
    op.create_index(
        "uq_service_account_secret_current",
        "service_account_secret",
        ["service_account_id"],
        unique=True,
        postgresql_where=sa.text("expires_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_service_account_secret_current", table_name="service_account_secret"
    )
    op.drop_index(
        "ix_service_account_secret_service_account_id",
        table_name="service_account_secret",
    )
    op.drop_table("service_account_secret")
    op.drop_table("service_account")
    bind = op.get_bind()
    service_account_status_type.drop(bind)
    machine_scope_type.drop(bind)
