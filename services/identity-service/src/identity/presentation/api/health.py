import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.infrastructure.persistence.health import ping_database
from identity.presentation.api.dependencies.services import get_session_factory

logger = logging.getLogger(__name__)

DATABASE_CHECK_TIMEOUT_SECONDS = 2.0

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> dict[str, str] | JSONResponse:
    try:
        await asyncio.wait_for(
            ping_database(session_factory),
            timeout=DATABASE_CHECK_TIMEOUT_SECONDS,
        )
    except (SQLAlchemyError, OSError, asyncio.TimeoutError):
        logger.warning("Readiness check failed: database is unavailable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable"},
        )
    return {"status": "ok"}
