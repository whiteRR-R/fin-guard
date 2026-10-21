from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._committed = False

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._committed:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self._session.rollback()
        self._committed = False
