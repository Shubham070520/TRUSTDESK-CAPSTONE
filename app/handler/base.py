import re
from typing import Any, Callable, ClassVar

from fastapi.responses import JSONResponse

from app.common.exceptions import AppException, ValidationError
from app.common.ids import UuidChecker
from app.common.logger import Logger
from app.common.response import ResponseBuilder
from app.config import Config, ErrorCode, ErrorConfig


class BaseHandler:
    """HTTP concerns only: validate input, call helpers, shape the response."""

    _IDENTIFIER: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")

    def __init__(self, logger: Logger, responses: ResponseBuilder | None = None) -> None:
        self._logger = logger
        self._responses = responses if responses is not None else ResponseBuilder()

    def return_json(
        self,
        success: bool,
        message: str,
        data: Any = None,
        error_code: int | None = None,
        status_code: int = 200,
    ) -> JSONResponse:
        return self._responses.json(
            success=success,
            message=message,
            data=data,
            error_code=error_code,
            status_code=status_code,
        )

    def execute(
        self,
        action: Callable[[], Any],
        success_message: str,
        status_code: int = 200,
    ) -> JSONResponse:
        """Run a helper call and turn the outcome into the envelope.

        ``AppException`` becomes its own error response. Anything else is
        logged with a stack trace and mapped to the generic 500 code.
        """
        try:
            data = action()
        except AppException as exc:
            return self._error_response(exc)
        except Exception:
            self._logger.exception("Unhandled exception in handler")
            return self.return_json(
                success=False,
                message=ErrorConfig.message(ErrorCode.INTERNAL),
                error_code=int(ErrorCode.INTERNAL),
                status_code=ErrorConfig.status(ErrorCode.INTERNAL),
            )
        return self.return_json(True, success_message, data, status_code=status_code)

    def validate_uuid(self, value: str) -> str:
        if not UuidChecker.is_valid(value):
            raise ValidationError(details={"uuid": value})
        return value

    def validate_identifier(self, value: str, field: str) -> str:
        """Business ids such as ``tkt_9001``: letters, digits, ``_`` and ``-``."""
        if not isinstance(value, str) or not self._IDENTIFIER.match(value):
            raise ValidationError(details={field: value})
        return value

    def validate_pagination(self, page: int, page_size: int) -> tuple[int, int]:
        if page < 1 or page_size < 1 or page_size > Config.MAX_PAGE_SIZE:
            raise ValidationError(
                details={
                    "page": page,
                    "page_size": page_size,
                    "max_page_size": Config.MAX_PAGE_SIZE,
                }
            )
        return page, page_size

    def _error_response(self, exc: AppException) -> JSONResponse:
        return self.return_json(
            success=False,
            message=exc.message,
            data=exc.details,
            error_code=int(exc.error_code),
            status_code=exc.http_status,
        )
