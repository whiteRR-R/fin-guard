from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RefreshAccessTokenResult:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
