"""Error codes, messages and HTTP statuses. No inline error strings elsewhere."""
from enum import IntEnum
from typing import ClassVar


class ErrorCode(IntEnum):
    INTERNAL = 1000
    VALIDATION = 1001
    AUTHENTICATION = 1002
    AUTHORIZATION = 1003
    NOT_FOUND = 1004
    GUARDRAIL = 1005
    CONFLICT = 1006
    TOOL_EXECUTION = 1007
    PROVIDER = 1008
    METHOD_NOT_ALLOWED = 1009
    DATABASE = 1010


class ErrorConfig:
    MESSAGES: ClassVar[dict[ErrorCode, str]] = {
        ErrorCode.INTERNAL: "Unexpected server error",
        ErrorCode.VALIDATION: "Request validation failed",
        ErrorCode.AUTHENTICATION: "Authentication failed",
        ErrorCode.AUTHORIZATION: "You are not allowed to perform this action",
        ErrorCode.NOT_FOUND: "Resource not found",
        ErrorCode.GUARDRAIL: "Request blocked by a safety guardrail",
        ErrorCode.CONFLICT: "Request conflicts with the current state",
        ErrorCode.TOOL_EXECUTION: "Tool execution failed",
        ErrorCode.PROVIDER: "AI provider failed or timed out",
        ErrorCode.METHOD_NOT_ALLOWED: "Method not allowed",
        ErrorCode.DATABASE: "Database is unavailable",
    }

    HTTP_STATUS: ClassVar[dict[ErrorCode, int]] = {
        ErrorCode.INTERNAL: 500,
        ErrorCode.VALIDATION: 422,
        ErrorCode.AUTHENTICATION: 401,
        ErrorCode.AUTHORIZATION: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.GUARDRAIL: 400,
        ErrorCode.CONFLICT: 409,
        ErrorCode.TOOL_EXECUTION: 502,
        ErrorCode.PROVIDER: 504,
        ErrorCode.METHOD_NOT_ALLOWED: 405,
        ErrorCode.DATABASE: 503,
    }

    # Maps raw HTTP statuses raised by the framework onto our codes.
    FROM_HTTP_STATUS: ClassVar[dict[int, ErrorCode]] = {
        401: ErrorCode.AUTHENTICATION,
        403: ErrorCode.AUTHORIZATION,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
    }

    @classmethod
    def message(cls, code: ErrorCode) -> str:
        return cls.MESSAGES[code]

    @classmethod
    def status(cls, code: ErrorCode) -> int:
        return cls.HTTP_STATUS[code]

    @classmethod
    def code_for_http_status(cls, status_code: int) -> ErrorCode:
        return cls.FROM_HTTP_STATUS.get(status_code, ErrorCode.INTERNAL)
