import importlib
import pkgutil
from dataclasses import dataclass

import pytest

import identity.application.messages as messages_package
from identity.application.messages.base import OutboxMessage

EXPECTED_MESSAGE_TYPES = {
    "AllSessionsLoggedOutMessage": "AllSessionsLoggedOut",
    "ClientSecretRotatedMessage": "ClientSecretRotated",
    "EmployeeBlockedMessage": "EmployeeBlocked",
    "EmployeeEmailChangedMessage": "EmployeeEmailChanged",
    "EmployeePasswordChangedMessage": "EmployeePasswordChanged",
    "EmployeeRoleAssignedMessage": "EmployeeRoleAssigned",
    "EmployeeRoleRevokedMessage": "EmployeeRoleRevoked",
    "EmployeeUnblockedMessage": "EmployeeUnblocked",
    "FirstAdminBootstrappedMessage": "FirstAdminBootstrapped",
    "InvitationAcceptedMessage": "InvitationAccepted",
    "InvitationEmailRequestedMessage": "InvitationEmailRequested",
    "InvitationRevokedMessage": "InvitationRevoked",
    "RefreshTokenReuseDetectedMessage": "RefreshTokenReuseDetected",
    "ServiceAccountCreatedMessage": "ServiceAccountCreated",
    "ServiceAccountRevokedMessage": "ServiceAccountRevoked",
    "SessionLoggedOutMessage": "SessionLoggedOut",
    "SessionRevokedMessage": "SessionRevoked",
}


def _message_classes() -> dict[str, type[OutboxMessage]]:
    found: dict[str, type[OutboxMessage]] = {}
    for module_info in pkgutil.iter_modules(messages_package.__path__):
        module = importlib.import_module(
            f"{messages_package.__name__}.{module_info.name}"
        )
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, OutboxMessage)
                and value is not OutboxMessage
            ):
                found[value.__name__] = value
    return found


def test_stored_message_types_are_stable() -> None:
    classes = _message_classes()

    assert {
        name: cls.message_type for name, cls in classes.items()
    } == EXPECTED_MESSAGE_TYPES


def test_message_types_are_unique() -> None:
    types = [cls.message_type for cls in _message_classes().values()]

    assert len(types) == len(set(types))


def test_every_message_declares_version() -> None:
    for cls in _message_classes().values():
        assert "version" in cls.__dataclass_fields__, cls.__name__


def test_message_without_message_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="message_type"):

        @dataclass(frozen=True, slots=True, kw_only=True)
        class UntypedMessage(OutboxMessage):
            value: int
