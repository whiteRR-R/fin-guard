from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RefreshAccessTokenCommand:
    refresh_token: str = field(repr=False)
