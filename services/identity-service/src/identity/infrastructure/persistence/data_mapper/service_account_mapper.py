from identity.domain.aggregates.service_account import ClientSecret, ServiceAccount
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ClientSecretId,
    ServiceAccountId,
    ServiceAccountName,
)
from identity.infrastructure.persistence.models.service_account import (
    ServiceAccountModel,
    ServiceAccountSecretModel,
)


class ServiceAccountMapper:
    @staticmethod
    def to_domain(model: ServiceAccountModel) -> ServiceAccount:
        return ServiceAccount.restore(
            service_account_id=ServiceAccountId(model.id),
            client_id=ClientId(model.client_id),
            name=ServiceAccountName(model.name),
            scopes=model.scopes,
            status=model.status,
            secrets=[
                ClientSecret(
                    secret_id=ClientSecretId(secret.id),
                    secret_hash=ClientSecretHash(secret.secret_hash),
                    created_at=secret.created_at,
                    expires_at=secret.expires_at,
                    revoked_at=secret.revoked_at,
                )
                for secret in model.secrets
            ],
            created_by=EmployeeId(model.created_by),
            created_at=model.created_at,
            revoked_at=model.revoked_at,
            last_used_at=model.last_used_at,
        )

    @staticmethod
    def to_model(account: ServiceAccount) -> ServiceAccountModel:
        model = ServiceAccountModel(
            id=account.id.value,
            client_id=account.client_id.value,
            name=account.name.value,
            scopes=ServiceAccountMapper._scopes(account),
            status=account.status,
            created_by=account.created_by.value,
            created_at=account.created_at,
            revoked_at=account.revoked_at,
            last_used_at=account.last_used_at,
        )
        model.secrets = [
            ServiceAccountMapper._secret_model(account, secret)
            for secret in account.secrets
        ]
        return model

    @staticmethod
    def update_model(account: ServiceAccount, model: ServiceAccountModel) -> None:
        if model.id != account.id.value:
            raise ValueError("Service account ID does not match model ID")

        model.client_id = account.client_id.value
        model.name = account.name.value
        model.scopes = ServiceAccountMapper._scopes(account)
        model.status = account.status
        model.created_by = account.created_by.value
        model.created_at = account.created_at
        model.revoked_at = account.revoked_at
        model.last_used_at = account.last_used_at

        existing = {secret.id: secret for secret in model.secrets}
        synced: list[ServiceAccountSecretModel] = []
        for secret in account.secrets:
            secret_model = existing.get(secret.id.value)
            if secret_model is None:
                secret_model = ServiceAccountMapper._secret_model(account, secret)
            else:
                secret_model.secret_hash = secret.secret_hash.value
                secret_model.created_at = secret.created_at
                secret_model.expires_at = secret.expires_at
                secret_model.revoked_at = secret.revoked_at
            synced.append(secret_model)
        model.secrets = synced

    @staticmethod
    def _scopes(account: ServiceAccount):
        return sorted(account.scopes, key=lambda scope: scope.value)

    @staticmethod
    def _secret_model(
        account: ServiceAccount, secret: ClientSecret
    ) -> ServiceAccountSecretModel:
        return ServiceAccountSecretModel(
            id=secret.id.value,
            service_account_id=account.id.value,
            secret_hash=secret.secret_hash.value,
            created_at=secret.created_at,
            expires_at=secret.expires_at,
            revoked_at=secret.revoked_at,
        )
