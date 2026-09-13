from collections.abc import Iterable
from datetime import datetime
from types import TracebackType

from identity.application.ports.security.access_token_issuer import (
    IssuedAccessToken,
)
from identity.application.ports.security.access_token_verifier import (
    AccessTokenClaims,
)
from identity.application.ports.security.invitation_token_issuer import (
    IssuedInvitationToken,
)
from identity.application.ports.security.refresh_token_issuer import (
    IssuedRefreshToken,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.password import HashedPassword, Password
from identity.domain.value_objects.refresh_session import RefreshSessionId


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class EmailSenderSpy:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[Email, str]] = []

    async def send(self, email: Email, plain_token: str) -> None:
        self.sent_messages.append((email, plain_token))


class EmployeeRepositoryFake:
    def __init__(self, employees: Iterable[EmployeeAccount] = ()) -> None:
        self._employees = {employee.id: employee for employee in employees}
        self.requested_ids: list[EmployeeId] = []
        self.requested_emails: list[Email] = []
        self.added: list[EmployeeAccount] = []
        self.saved: list[EmployeeAccount] = []

    async def get_by_id(self, id: EmployeeId) -> EmployeeAccount | None:
        self.requested_ids.append(id)
        return self._employees.get(id)

    async def get_by_email(self, email: Email) -> EmployeeAccount | None:
        self.requested_emails.append(email)
        return next(
            (employee for employee in self._employees.values() if employee.email == email),
            None,
        )

    async def add(self, employee: EmployeeAccount) -> None:
        self._employees[employee.id] = employee
        self.added.append(employee)

    async def save(self, employee: EmployeeAccount) -> None:
        self._employees[employee.id] = employee
        self.saved.append(employee)


class InvitationRepositoryFake:
    def __init__(self, invitations: Iterable[Invitation] = ()) -> None:
        self._invitations = {
            invitation.id: invitation for invitation in invitations
        }
        self.added: list[Invitation] = []
        self.saved: list[Invitation] = []

    async def get_by_id(self, invitation_id: InvitationId) -> Invitation | None:
        return self._invitations.get(invitation_id)

    async def add(self, invitation: Invitation) -> None:
        self._invitations[invitation.id] = invitation
        self.added.append(invitation)

    async def save(self, invitation: Invitation) -> None:
        self._invitations[invitation.id] = invitation
        self.saved.append(invitation)


class RefreshSessionRepositoryFake:
    def __init__(
        self,
        *,
        active_at: datetime,
        sessions: Iterable[RefreshSession] = (),
    ) -> None:
        self._active_at = active_at
        self._sessions = {session.id: session for session in sessions}
        self.requested_ids: list[RefreshSessionId] = []
        self.requested_employee_ids: list[EmployeeId] = []
        self.added: list[RefreshSession] = []
        self.saved: list[RefreshSession] = []

    async def get_by_id(
        self,
        session_id: RefreshSessionId,
    ) -> RefreshSession | None:
        self.requested_ids.append(session_id)
        return self._sessions.get(session_id)

    async def list_active_by_user(
        self,
        user_id: EmployeeId,
    ) -> list[RefreshSession]:
        self.requested_employee_ids.append(user_id)
        return [
            session
            for session in self._sessions.values()
            if session.employee_id == user_id and session.is_active(self._active_at)
        ]

    async def add(self, refresh_session: RefreshSession) -> None:
        self._sessions[refresh_session.id] = refresh_session
        self.added.append(refresh_session)

    async def save(self, refresh_session: RefreshSession) -> None:
        self._sessions[refresh_session.id] = refresh_session
        self.saved.append(refresh_session)


class UnitOfWorkFake:
    def __init__(
        self,
        *,
        active_at: datetime,
        employees: Iterable[EmployeeAccount] = (),
        invitations: Iterable[Invitation] = (),
        sessions: Iterable[RefreshSession] = (),
    ) -> None:
        self.employees = EmployeeRepositoryFake(employees)
        self.invitations = InvitationRepositoryFake(invitations)
        self.refresh_sessions = RefreshSessionRepositoryFake(
            active_at=active_at,
            sessions=sessions,
        )
        self.commit_count = 0
        self.rollback_count = 0

    async def __aenter__(self) -> "UnitOfWorkFake":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class PasswordHasherStub:
    def __init__(
        self,
        *,
        password_is_valid: bool,
        hash_result: HashedPassword | None = None,
    ) -> None:
        self._password_is_valid = password_is_valid
        self._hash_result = hash_result or HashedPassword("new-password-hash")
        self.verify_calls: list[tuple[Password, HashedPassword]] = []
        self.hash_calls: list[Password] = []

    def verify(self, password: Password, hashed_password: HashedPassword) -> bool:
        self.verify_calls.append((password, hashed_password))
        return self._password_is_valid

    def hash(self, password: Password) -> HashedPassword:
        self.hash_calls.append(password)
        return self._hash_result


class AccessTokenIssuerStub:
    def __init__(self, result: IssuedAccessToken) -> None:
        self._result = result
        self.calls: list[
            tuple[EmployeeId, RefreshSessionId, frozenset[EmployeeRole], datetime]
        ] = []

    def issue(
        self,
        user_id: EmployeeId,
        session_id: RefreshSessionId,
        roles: frozenset[EmployeeRole],
        issued_at: datetime,
    ) -> IssuedAccessToken:
        self.calls.append((user_id, session_id, roles, issued_at))
        return self._result


class RefreshTokenIssuerStub:
    def __init__(self, result: IssuedRefreshToken) -> None:
        self._result = result
        self.calls: list[RefreshSessionId] = []

    def issue(self, session_id: RefreshSessionId) -> IssuedRefreshToken:
        self.calls.append(session_id)
        return self._result


class InvitationTokenIssuerStub:
    def __init__(self, result: IssuedInvitationToken) -> None:
        self._result = result
        self.calls: list[tuple[InvitationId, EmployeeId, Email, datetime]] = []

    def issue(
        self,
        invitation_id: InvitationId,
        invited_by: EmployeeId,
        employee_email: Email,
        issued_at: datetime,
    ) -> IssuedInvitationToken:
        self.calls.append(
            (invitation_id, invited_by, employee_email, issued_at)
        )
        return self._result


class AccessTokenVerifierStub:
    def __init__(self, claims: AccessTokenClaims) -> None:
        self._claims = claims
        self.received_tokens: list[str] = []

    def verify(self, access_token: str) -> AccessTokenClaims:
        self.received_tokens.append(access_token)
        return self._claims
