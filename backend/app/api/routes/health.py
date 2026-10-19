import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(session: SessionDep) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        # Only the exception class is logged: driver messages can include the host.
        logger.warning(
            "health check: database unreachable", extra={"exc_class": type(exc).__name__}
        )
        return JSONResponse(
            status_code=503, content={"status": "degraded", "database": "unavailable"}
        )
    return JSONResponse(content={"status": "ok", "database": "connected"})
