"""Typed application exceptions.

Helpers raise these. Handlers catch ``AppException`` and turn it into the
response envelope. Messages come from ``ErrorConfig``.
"""
from typing import Any, ClassVar

from app.config import ErrorCode, ErrorConfig


class AppException(Exception):
    """Base class. Carries the numeric error code and the HTTP status."""

    DEFAULT_CODE: ClassVar[ErrorCode] = ErrorCode.INTERNAL

    def __init__(
        self,
        error_code: ErrorCode | None = None,
        details: Any = None,
        http_status: int | None = None,
    ) -> None:
        code = error_code if error_code is not None else self.DEFAULT_CODE
        self._error_code = code
        self._http_status = http_status if http_status is not None else ErrorConfig.status(code)
        self._details = details
        super().__init__(ErrorConfig.message(code))

    @property
    def error_code(self) -> ErrorCode:
        return self._error_code

    @property
    def http_status(self) -> int:
        return self._http_status

    @property
    def message(self) -> str:
        return ErrorConfig.message(self._error_code)

    @property
    def details(self) -> Any:
        return self._details


class ValidationError(AppException):
    DEFAULT_CODE = ErrorCode.VALIDATION


class AuthenticationError(AppException):
    DEFAULT_CODE = ErrorCode.AUTHENTICATION


class AuthorizationError(AppException):
    DEFAULT_CODE = ErrorCode.AUTHORIZATION


class NotFoundError(AppException):
    DEFAULT_CODE = ErrorCode.NOT_FOUND


class GuardrailError(AppException):
    DEFAULT_CODE = ErrorCode.GUARDRAIL


class ConflictError(AppException):
    DEFAULT_CODE = ErrorCode.CONFLICT


class ToolExecutionError(AppException):
    DEFAULT_CODE = ErrorCode.TOOL_EXECUTION


class ToolNotEnabledError(AppException):
    DEFAULT_CODE = ErrorCode.TOOL_NOT_ENABLED


class ProviderError(AppException):
    DEFAULT_CODE = ErrorCode.PROVIDER


class DatabaseError(AppException):
    DEFAULT_CODE = ErrorCode.DATABASE
