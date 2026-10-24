"""Create employee, invitation, and session tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2a71f5b0c38"
down_revision: str | None = "b7c84a19d5e2"
branch_labels: str | None = None
depends_on: str | None = None


employee_role_type = postgresql.ENUM(
    "ADMIN",
    "RISK_ANALYST",
    "COMPLIANCE_OFFICER",
    "AUDITOR",
    name="employee_role",
    create_type=False,
)
employee_status_type = postgresql.ENUM(
    "INVITED",
    "ACTIVE",
    "BLOCKED",
    "DEACTIVATED",
    name="employee_status",
    create_type=False,
)
invitation_status_type = postgresql.ENUM(
    "PENDING",
    "ACCEPTED",
    "REVOKED",
    name="invitation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    employee_role_type.create(bind)
    employee_status_type.create(bind)
    invitation_status_type.create(bind)

    op.create_table(
        "employee",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("roles", postgresql.ARRAY(employee_role_type), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("status", employee_status_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_employee_email_lower",
        "employee",
        [sa.text("lower(email)")],
        unique=True,
    )

    op.create_table(
        "invitation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("invited_email", sa.String(length=254), nullable=False),
        sa.Column("roles", postgresql.ARRAY(employee_role_type), nullable=False),
        sa.Column("status", invitation_status_type, nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("cardinality(roles) > 0", name="ck_invitation_roles_nonempty"),
        sa.ForeignKeyConstraint(["invited_by"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitation_invited_email", "invitation", ["invited_email"])

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("session")
    op.drop_index("ix_invitation_invited_email", table_name="invitation")
    op.drop_table("invitation")
    op.drop_index("uq_employee_email_lower", table_name="employee")
    op.drop_table("employee")

    bind = op.get_bind()
    invitation_status_type.drop(bind)
    employee_status_type.drop(bind)
    employee_role_type.drop(bind)
