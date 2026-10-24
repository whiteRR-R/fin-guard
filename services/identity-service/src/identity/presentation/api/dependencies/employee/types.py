from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.assign_role.handler import AssignRoleHandler
from identity.application.commands.block_employee.handler import BlockEmployeeHandler
from identity.application.commands.change_email.handler import ChangeEmailHandler
from identity.application.commands.change_password.handler import ChangePasswordHandler
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.application.commands.revoke_role.handler import RevokeRoleHandler
from identity.application.commands.unblock_employee.handler import (
    UnblockEmployeeHandler,
)
from identity.application.ports.clock import Clock
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.access_token_verifier import (
    AccessTokenVerifier,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer
from identity.application.queries.get_current_employee.handler import (
    GetCurrentEmployeeHandler,
)
from identity.application.queries.get_employee.handler import GetEmployeeHandler
from identity.application.queries.list_employees.handler import ListEmployeesHandler
from identity.presentation.api.dependencies.types import Provider

@dataclass(frozen=True)
class EmployeeApiServices:
    session_factory: async_sessionmaker[AsyncSession]
    clock: Clock
    password_hasher: PasswordHasher
    access_token_issuer: AccessTokenIssuer
    access_token_verifier: AccessTokenVerifier
    refresh_token_issuer: RefreshTokenIssuer
    refresh_token_lifetime: timedelta


@dataclass(frozen=True)
class EmployeeDependencies:
    actor: Provider[CurrentActor]
    login: Provider[LoginEmployeeHandler]
    current_employee: Provider[GetCurrentEmployeeHandler]
    change_email: Provider[ChangeEmailHandler]
    change_password: Provider[ChangePasswordHandler]
    list_employees: Provider[ListEmployeesHandler]
    get_employee: Provider[GetEmployeeHandler]
    block_employee: Provider[BlockEmployeeHandler]
    unblock_employee: Provider[UnblockEmployeeHandler]
    assign_role: Provider[AssignRoleHandler]
    revoke_role: Provider[RevokeRoleHandler]
