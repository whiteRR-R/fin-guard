from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.ports.clock import Clock
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.access_token_verifier import (
    AccessTokenVerifier,
)
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer


@dataclass(frozen=True)
class ApiServices:
    session_factory: async_sessionmaker[AsyncSession]
    clock: Clock
    password_hasher: PasswordHasher
    access_token_issuer: AccessTokenIssuer
    access_token_verifier: AccessTokenVerifier
    refresh_token_issuer: RefreshTokenIssuer
    refresh_token_lifetime: timedelta
    invitation_token_issuer: InvitationTokenIssuer
    invitation_token_verifier: InvitationTokenVerifier


def _services(request: Request) -> ApiServices:
    return cast(ApiServices, request.app.state.identity_services)


async def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return _services(request).session_factory


async def get_clock(request: Request) -> Clock:
    return _services(request).clock


async def get_password_hasher(request: Request) -> PasswordHasher:
    return _services(request).password_hasher


async def get_access_token_issuer(request: Request) -> AccessTokenIssuer:
    return _services(request).access_token_issuer


async def get_access_token_verifier(request: Request) -> AccessTokenVerifier:
    return _services(request).access_token_verifier


async def get_refresh_token_issuer(request: Request) -> RefreshTokenIssuer:
    return _services(request).refresh_token_issuer


async def get_refresh_token_lifetime(request: Request) -> timedelta:
    return _services(request).refresh_token_lifetime


async def get_invitation_token_issuer(request: Request) -> InvitationTokenIssuer:
    return _services(request).invitation_token_issuer


async def get_invitation_token_verifier(request: Request) -> InvitationTokenVerifier:
    return _services(request).invitation_token_verifier


AsyncSessionFactoryDependency = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]
ClockDependency = Annotated[Clock, Depends(get_clock)]
PasswordHasherDependency = Annotated[PasswordHasher, Depends(get_password_hasher)]
AccessTokenIssuerDependency = Annotated[
    AccessTokenIssuer, Depends(get_access_token_issuer)
]
AccessTokenVerifierDependency = Annotated[
    AccessTokenVerifier, Depends(get_access_token_verifier)
]
RefreshTokenIssuerDependency = Annotated[
    RefreshTokenIssuer, Depends(get_refresh_token_issuer)
]
RefreshTokenLifetimeDependency = Annotated[
    timedelta, Depends(get_refresh_token_lifetime)
]
InvitationTokenIssuerDependency = Annotated[
    InvitationTokenIssuer, Depends(get_invitation_token_issuer)
]
InvitationTokenVerifierDependency = Annotated[
    InvitationTokenVerifier, Depends(get_invitation_token_verifier)
]
