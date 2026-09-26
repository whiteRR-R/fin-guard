from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.exceptions import (
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    SessionIsNotActiveError,
    SessionNotFoundError,
)
from identity.application.messages.refresh_token_reuse_detected import (
    RefreshTokenReuseDetected,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer
from identity.application.ports.security.refresh_token_verifier import (
    RefreshTokenVerifier,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.status import EmployeeStatus


class RefreshAccessTokenHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        refresh_session_repository: RefreshSessionRepository,
        employee_repository: EmployeeRepository,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
        refresh_token_verifier: RefreshTokenVerifier,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._refresh_session_repository = refresh_session_repository
        self._employee_repository = employee_repository
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._refresh_token_verifier = refresh_token_verifier
        self._outbox_repository = outbox_repository

    async def execute(
        self,
        command: RefreshAccessTokenCommand,
    ) -> RefreshAccessTokenResult:
        claims = self._refresh_token_verifier.verify(command.refresh_token)

        async with self._uow:
            session = await self._refresh_session_repository.get_by_id_with_lock(
                claims.session_id
            )
            now = self._clock.now()

            if claims.expires_at <= now:
                raise InvalidRefreshTokenError("Refresh token expired")

            if session is None:
                raise SessionNotFoundError("Session not found")

            if not session.is_active(now):
                raise SessionIsNotActiveError("Session must be active")

            employee = await self._employee_repository.get_by_id(session.employee_id)

            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if employee.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Employee must be active")

            token_matches_current_hash = self._refresh_token_verifier.matches_hash(
                command.refresh_token,
                session.refresh_token_hash,
            )
            used_refresh_token_hashes = (
                await self._refresh_session_repository.list_used_refresh_token_hashes(
                    session.id
                )
            )

            if not token_matches_current_hash:
                token_was_used = any(
                    self._refresh_token_verifier.matches_hash(
                        command.refresh_token,
                        token_hash,
                    )
                    for token_hash in used_refresh_token_hashes
                )

                if not token_was_used:
                    raise InvalidRefreshTokenError("Invalid refresh token")

                session.revoke(now)
                outbox_message = RefreshTokenReuseDetected(
                    session_id=session.id.value,
                    employee_id=employee.id.value,
                    created_at=now,
                )
                await self._outbox_repository.add(outbox_message)
            else:
                issued_refresh_token = self._refresh_token_issuer.issue(
                    session_id=session.id
                )
                previous_refresh_token_hash = session.refresh_token_hash
                new_refresh_token_hash = issued_refresh_token.token_hash

                if (
                    new_refresh_token_hash == previous_refresh_token_hash
                    or new_refresh_token_hash in used_refresh_token_hashes
                ):
                    raise InvalidRefreshTokenError(
                        "Refresh token issuer reused a token"
                    )

                issued_access_token = self._access_token_issuer.issue(
                    employee_id=employee.id,
                    session_id=session.id,
                    roles=employee.roles,
                    issued_at=now,
                )
                session.rotate(new_token_hash=new_refresh_token_hash, now=now)

                await self._refresh_session_repository.add_used_refresh_token_hash(
                    session.id,
                    previous_refresh_token_hash,
                )

            await self._refresh_session_repository.save(session)
            await self._uow.commit()

        if not token_matches_current_hash:
            raise RefreshTokenReuseError("Refresh token has already been used")

        return RefreshAccessTokenResult(
            access_token=issued_access_token.plain_token,
            refresh_token=issued_refresh_token.plain_token,
        )
