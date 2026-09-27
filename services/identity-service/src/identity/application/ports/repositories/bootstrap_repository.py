from typing import Protocol


class BootstrapRepository(Protocol):
    async def try_claim_first_admin(self) -> bool: ...
