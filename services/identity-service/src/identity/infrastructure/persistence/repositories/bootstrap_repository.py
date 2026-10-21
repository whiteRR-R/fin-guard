from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class BootstrapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_claim_first_admin(self) -> bool:
        return bool(
            await self._session.scalar(
                text("SELECT pg_try_advisory_xact_lock(631992472002)")
            )
        )
