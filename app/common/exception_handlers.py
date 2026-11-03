from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.exceptions import AppException
from app.common.logger import Logger
from app.common.response import ResponseBuilder
from app.config import ErrorCode, ErrorConfig


class ExceptionHandlerRegistry:
    """Maps framework-level and unexpected errors onto the response envelope.

    Errors raised inside handlers are already converted by ``BaseHandler``.
    This covers what happens before a handler runs (unknown route, bad query
    parameters) and anything that escapes.
    """

    def __init__(self, logger: Logger, responses: ResponseBuilder) -> None:
        self._logger = logger
        self._responses = responses

    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(AppException, self._on_app_exception)
        app.add_exception_handler(RequestValidationError, self._on_request_validation)
        app.add_exception_handler(StarletteHTTPException, self._on_http_exception)
        app.add_exception_handler(Exception, self._on_unexpected)

    async def _on_app_exception(self, _: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppException)
        headers = {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None
        return self._error(exc.error_code, exc.http_status, exc.details, headers)

    async def _on_request_validation(self, _: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        details: list[dict[str, Any]] = [
            {"loc": list(e.get("loc", [])), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return self._error(
            ErrorCode.VALIDATION, ErrorConfig.status(ErrorCode.VALIDATION), details
        )

    async def _on_http_exception(self, _: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = ErrorConfig.code_for_http_status(exc.status_code)
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return self._error(code, exc.status_code, None, headers)

    async def _on_unexpected(self, _: Request, exc: Exception) -> JSONResponse:
        self._logger.exception("Unhandled exception")
        return self._error(ErrorCode.INTERNAL, ErrorConfig.status(ErrorCode.INTERNAL))

    def _error(
        self,
        code: ErrorCode,
        status_code: int,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return self._responses.json(
            success=False,
            message=ErrorConfig.message(code),
            data=details,
            error_code=int(code),
            status_code=status_code,
            headers=headers,
        )
