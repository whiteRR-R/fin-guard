from identity.application.commands.issue_machine_access_token.command import (
    IssueMachineAccessTokenCommand,
)
from identity.application.commands.issue_machine_access_token.result import (
    IssueMachineAccessTokenResult,
)
from identity.application.exceptions import InvalidClientError, InvalidScopeError
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from identity.application.ports.security.client_credentials import (
    ClientSecretVerifier,
)
from identity.application.ports.security.machine_token_issuer import (
    MachineTokenIssuer,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.scope import MachineScope
from identity.domain.exceptions import (
    ScopeNotGrantedError,
    ServiceAccountValidationError,
)
from identity.domain.value_objects.service_account import ClientId, ClientSecretHash

_DUMMY_SECRET_HASH = ClientSecretHash("0" * 64)


class IssueMachineAccessTokenHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        service_accounts: ServiceAccountRepository,
        secret_verifier: ClientSecretVerifier,
        token_issuer: MachineTokenIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._service_accounts = service_accounts
        self._secret_verifier = secret_verifier
        self._token_issuer = token_issuer

    async def execute(
        self, command: IssueMachineAccessTokenCommand
    ) -> IssueMachineAccessTokenResult:
        requested_scopes = self._parse_scopes(command.scopes)

        try:
            client_id = ClientId(command.client_id)
        except ServiceAccountValidationError as error:
            raise InvalidClientError("Invalid client") from error

        async with self._uow:
            account = await self._service_accounts.get_by_client_id(client_id)
            now = self._clock.now()

            if account is None:
                self._secret_verifier.matches(command.client_secret, _DUMMY_SECRET_HASH)
                raise InvalidClientError("Invalid client")

            secret_matches = any(
                self._secret_verifier.matches(command.client_secret, secret.secret_hash)
                for secret in account.active_secrets(now)
            )

            if not secret_matches:
                raise InvalidClientError("Invalid client")

            try:
                scopes = account.authorize_scopes(requested_scopes)
            except ScopeNotGrantedError as error:
                raise InvalidScopeError("Requested scope is not granted") from error

            token = self._token_issuer.issue(
                service_account_id=account.id,
                client_id=account.client_id,
                scopes=scopes,
                issued_at=now,
            )

            if account.record_usage(now):
                await self._service_accounts.save_last_used_at(account)
                await self._uow.commit()

        return IssueMachineAccessTokenResult(
            access_token=token.plain_token,
            expires_at=token.expires_at,
            scopes=tuple(sorted(scopes, key=lambda scope: scope.value)),
        )

    @staticmethod
    def _parse_scopes(raw: tuple[str, ...] | None) -> frozenset[MachineScope] | None:
        if raw is None:
            return None
        try:
            return frozenset(MachineScope(value) for value in raw)
        except ValueError as error:
            raise InvalidScopeError("Unknown scope") from error
