from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoginEmployeeCommand:
    email: str
    password: str = field(repr=False)
    
