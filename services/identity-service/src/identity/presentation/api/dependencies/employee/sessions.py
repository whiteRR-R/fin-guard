from identity.application.commands.logout.handler import LogoutHandler
from identity.application.commands.logout_all_sessions.handler import (
    LogoutAllSessionsHandler,
)
from identity.application.commands.refresh_access_token.handler import (
    RefreshAccessTokenHandler,
)
from identity.application.commands.revoke_own_session.handler import (
    RevokeOwnSessionHandler,
)
from identity.application.queries.list_own_sessions.handler import (
    ListOwnSessionsHandler,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    OutboxRepositoryDependency,
    RefreshSessionRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    AccessTokenIssuerDependency,
    ClockDependency,
    RefreshTokenIssuerDependency,
    RefreshTokenVerifierDependency,
)


async def get_refresh_access_token_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    access_token_issuer: AccessTokenIssuerDependency,
    refresh_token_issuer: RefreshTokenIssuerDependency,
    refresh_token_verifier: RefreshTokenVerifierDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    employees: EmployeeRepositoryDependency,
    outbox: OutboxRepositoryDependency,
) -> RefreshAccessTokenHandler:
    return RefreshAccessTokenHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_verifier=refresh_token_verifier,
        refresh_session_repository=refresh_sessions,
        employee_repository=employees,
        outbox_repository=outbox,
    )


async def get_logout_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    outbox: OutboxRepositoryDependency,
) -> LogoutHandler:
    return LogoutHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        refresh_session_repository=refresh_sessions,
        outbox_repository=outbox,
    )


async def get_logout_all_sessions_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    employees: EmployeeRepositoryDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    outbox: OutboxRepositoryDependency,
) -> LogoutAllSessionsHandler:
    return LogoutAllSessionsHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employee_repository=employees,
        refresh_session_repository=refresh_sessions,
        outbox_repository=outbox,
    )


async def get_list_own_sessions_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
) -> ListOwnSessionsHandler:
    return ListOwnSessionsHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        refresh_session_repository=refresh_sessions,
    )


async def get_revoke_own_session_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    outbox: OutboxRepositoryDependency,
) -> RevokeOwnSessionHandler:
    return RevokeOwnSessionHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        refresh_session_repository=refresh_sessions,
        outbox_repository=outbox,
    )
