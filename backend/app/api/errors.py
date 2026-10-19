import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.base import LLMError
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class DomainValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


def error_response(
    status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_var.get()}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    # Echoing `input` back could return a 200k-character draft or a secret.
    return [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError) -> JSONResponse:
        # LLMError messages are written to be user-safe (no keys, no prompts).
        status = {"llm_rate_limited": 503, "llm_timeout": 504}.get(exc.code, 502)
        response = error_response(status, exc.code, str(exc))
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            response.headers["Retry-After"] = str(int(retry_after))
        return response

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422, "validation_error", "Request validation failed", _validation_details(exc)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return error_response(exc.status_code, code, message)

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        # Driver messages may include SQL, parameters or host names: never return them.
        if isinstance(exc, OperationalError | InterfaceError) or exc.connection_invalidated:
            logger.error("database unavailable", extra={"exc_class": type(exc.orig).__name__})
            return error_response(503, "database_unavailable", "The database is unavailable")
        logger.error("database error", extra={"exc_class": type(exc.orig).__name__})
        return error_response(500, "internal_error", "An unexpected error occurred")

    # Unhandled exceptions become a 500 envelope in RequestIDMiddleware.
