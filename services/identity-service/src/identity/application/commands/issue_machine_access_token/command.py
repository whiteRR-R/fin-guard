from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IssueMachineAccessTokenCommand:
    client_id: str
    client_secret: str = field(repr=False)
    scopes: tuple[str, ...] | None = None
