from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BootstrapFirstAdminCommand:
    email: str
    password: str = field(repr=False)
