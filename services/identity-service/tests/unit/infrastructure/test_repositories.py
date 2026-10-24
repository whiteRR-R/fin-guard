import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from identity.application.messages.employee_role_assigned import EmployeeRoleAssigned
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import InvitationStatus
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from identity.domain.value_objects.password import HashedPassword
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from identity.infrastructure.persistence.data_mapper.employee_mapper import (
    EmployeeMapper,
)
from identity.infrastructure.persistence.data_mapper.invitation_mapper import (
    InvitationMapper,
)
from identity.infrastructure.persistence.data_mapper.refresh_session_mapper import (
    RefreshSessionMapper,
)
from identity.infrastructure.persistence.models.employee import EmployeeModel
from identity.infrastructure.persistence.models.invitation import InvitationModel
from identity.infrastructure.persistence.models.session import SessionModel
from identity.infrastructure.persistence.repositories.bootstrap_repository import (
    BootstrapRepository,
)
from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.infrastructure.persistence.repositories.outbox_repository import (
    OutboxRepository,
)
from identity.infrastructure.persistence.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)


def _session():
    session = Mock()
    session.get = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    return session


def _sql(statement):
    return str(statement.compile(dialect=postgresql.dialect())).lower()


def test_employee_mapper_round_trip_and_save():
    employee = EmployeeAccount.create_admin(
        employee_id=EmployeeId.new(),
        email=Email("Admin@Example.com"),
        password_hash=HashedPassword("hashed-password"),
    )
    model = EmployeeMapper.to_model(employee)
    assert isinstance(model, EmployeeModel)
    assert EmployeeMapper.to_domain(model).email == employee.email

    repository_session = _session()
    repository_session.scalar.return_value = model
    repository = EmployeeRepository(repository_session)
    employee.block()
    asyncio.run(repository.save(employee))
    assert model.status == employee.status
    assert "for update" in _sql(repository_session.scalar.call_args.args[0])


def test_employee_repository_queries_use_admin_and_email_invariants():
    repository_session = _session()
    repository = EmployeeRepository(repository_session)
    asyncio.run(repository.count_active_admins())
    statement = repository_session.scalar.call_args.args[0]
    assert "any (employee.roles)" in _sql(statement)
    assert "employee.status" in _sql(statement)

    repository_session.scalar.return_value = None
    asyncio.run(repository.get_by_email_with_lock(Email("USER@EXAMPLE.COM")))
    statement = repository_session.scalar.call_args.args[0]
    assert "lower(employee.email)" in _sql(statement)
    assert "for update" in _sql(statement)

    asyncio.run(repository.lock_role_changes())
    assert "pg_advisory_xact_lock" in str(repository_session.execute.call_args.args[0])


def test_invitation_mapper_round_trip_and_latest_query():
    now = datetime.now(timezone.utc)
    invitation = Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_by=EmployeeId.new(),
        invited_email=Email("USER@EXAMPLE.COM"),
        roles=(EmployeeRole.AUDITOR,),
        token_hash=InvitationTokenHash("hash-only"),
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    model = InvitationMapper.to_model(invitation)
    assert isinstance(model, InvitationModel)
    restored = InvitationMapper.to_domain(model)
    assert restored.token_hash == invitation.token_hash
    assert restored.status is InvitationStatus.PENDING

    repository_session = _session()
    repository_session.get.return_value = model
    repository_session.scalar.return_value = model
    repository = InvitationRepository(repository_session)
    by_id = asyncio.run(repository.get_by_id(invitation.id))
    assert by_id is not None
    assert by_id.id == invitation.id
    result = asyncio.run(
        repository.get_latest_by_employee_email_with_lock(Email("user@example.com"))
    )
    assert result is not None
    assert result.id == invitation.id
    statement = repository_session.scalar.call_args.args[0]
    assert "lower(invitation.invited_email)" in _sql(statement)
    assert "created_at desc" in _sql(statement)
    assert "for update" in _sql(statement)
    assert "pg_advisory_xact_lock" in str(
        repository_session.execute.call_args.args[0]
    )
    assert repository_session.execute.call_args.args[1] == {
        "email": "user@example.com"
    }

    invitation.accept(now + timedelta(hours=1))
    asyncio.run(repository.save(invitation))
    assert model.status is InvitationStatus.ACCEPTED
    assert model.accepted_at == invitation.accepted_at


def test_refresh_session_repository_persists_rotation_and_history():
    now = datetime.now(timezone.utc)
    refresh_session = RefreshSession.start(
        session_id=RefreshSessionId.new(),
        employee_id=EmployeeId.new(),
        refresh_token_hash=RefreshTokenHash("old-hash"),
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    model = RefreshSessionMapper.to_model(refresh_session)
    assert isinstance(model, SessionModel)
    assert RefreshSessionMapper.to_domain(model).refresh_token_hash == RefreshTokenHash(
        "old-hash"
    )

    repository_session = _session()
    repository_session.scalar.return_value = model
    repository_session.scalars.return_value = ["old-hash"]
    repository = RefreshSessionRepository(repository_session)
    refresh_session.rotate(new_token_hash=RefreshTokenHash("new-hash"), now=now)
    asyncio.run(repository.save(refresh_session))
    assert model.refresh_token_hash == "new-hash"
    asyncio.run(
        repository.add_used_refresh_token_hash(
            refresh_session.id, RefreshTokenHash("old-hash")
        )
    )
    used = repository_session.add.call_args.args[0]
    assert used.session_id == refresh_session.id.value
    assert used.token_hash == "old-hash"
    assert asyncio.run(
        repository.list_used_refresh_token_hashes(refresh_session.id)
    ) == (RefreshTokenHash("old-hash"),)

    repository_session.scalars.return_value = [model]
    asyncio.run(
        repository.list_active_by_employee_with_lock(
            refresh_session.employee_id, active_at=now
        )
    )
    statement = repository_session.scalars.call_args.args[0]
    assert "revoked_at is null" in _sql(statement)
    assert "expires_at >" in _sql(statement)
    assert "for update" in _sql(statement)


def test_bootstrap_claim_and_outbox_serialization():
    repository_session = _session()
    repository_session.scalar.return_value = True
    assert asyncio.run(
        BootstrapRepository(repository_session).try_claim_first_admin()
    )
    assert "pg_try_advisory_xact_lock" in str(
        repository_session.scalar.call_args.args[0]
    )

    message = EmployeeRoleAssigned(
        employee_id=uuid4(), actor_id=uuid4(), role=EmployeeRole.ADMIN
    )
    asyncio.run(OutboxRepository(repository_session).add(message))
    model = repository_session.add.call_args.args[0]
    assert model.message_type == "EmployeeRoleAssigned"
    assert model.version == 1
    assert model.payload == {
        "employee_id": str(message.employee_id),
        "actor_id": str(message.actor_id),
        "role": "ADMIN",
    }

    invitation_message = InvitationEmailRequested(
        invitation_id=uuid4(), recipient_email="user@example.com"
    )
    asyncio.run(OutboxRepository(repository_session).add(invitation_message))
    model = repository_session.add.call_args.args[0]
    assert model.version == 1
    assert model.payload["invitation_id"] == str(invitation_message.invitation_id)
