from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.exception_handlers import ExceptionHandlerRegistry
from app.common.exceptions import (
    AppException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    GuardrailError,
    NotFoundError,
    ProviderError,
    ToolExecutionError,
    ValidationError,
)
from app.common.logger import Logger
from app.common.response import ResponseBuilder
from app.config import ErrorCode, ErrorConfig
from app.urls.base import BaseRouter

CASES: list[tuple[type[AppException], ErrorCode]] = [
    (ValidationError, ErrorCode.VALIDATION),
    (AuthenticationError, ErrorCode.AUTHENTICATION),
    (AuthorizationError, ErrorCode.AUTHORIZATION),
    (NotFoundError, ErrorCode.NOT_FOUND),
    (GuardrailError, ErrorCode.GUARDRAIL),
    (ConflictError, ErrorCode.CONFLICT),
    (ToolExecutionError, ErrorCode.TOOL_EXECUTION),
    (ProviderError, ErrorCode.PROVIDER),
    (DatabaseError, ErrorCode.DATABASE),
]


class TestExceptionHierarchy:
    @pytest.mark.parametrize("exc_cls,code", CASES)
    def test_defaults_come_from_config(
        self, exc_cls: type[AppException], code: ErrorCode
    ) -> None:
        exc = exc_cls()
        assert isinstance(exc, AppException)
        assert exc.error_code == code
        assert exc.http_status == ErrorConfig.status(code)
        assert exc.message == ErrorConfig.message(code)

    def test_details_and_status_override(self) -> None:
        exc = AppException(ErrorCode.CONFLICT, details={"k": 1}, http_status=418)
        assert exc.details == {"k": 1}
        assert exc.http_status == 418


class FailingRouter(BaseRouter):
    """Test-only router whose routes raise, to exercise the registry."""

    def register_routes(self) -> None:
        for exc_cls, code in CASES:
            self._router.add_api_route(
                f"/raise/{int(code)}", self._make_raiser(exc_cls), methods=["GET"]
            )
        self._router.add_api_route("/crash", self._crash, methods=["GET"])
        self._router.add_api_route("/needs-int", self._needs_int, methods=["GET"])

    def _make_raiser(self, exc_cls: type[AppException]) -> Any:
        return _Raiser(exc_cls)

    def _crash(self) -> None:
        raise RuntimeError("secret internals")

    def _needs_int(self, n: int) -> dict[str, int]:
        return {"n": n}


class _Raiser:
    def __init__(self, exc_cls: type[AppException]) -> None:
        self._exc_cls = exc_cls

    def __call__(self) -> None:
        raise self._exc_cls(details={"why": "test"})


class TestExceptionHandlerRegistry:
    @pytest.fixture()
    def client(self) -> TestClient:
        app = FastAPI()
        ExceptionHandlerRegistry(Logger("test"), ResponseBuilder()).register(app)
        app.include_router(FailingRouter(database=None, logger=Logger("test")).build())  # type: ignore[arg-type]
        return TestClient(app, raise_server_exceptions=False)

    @pytest.mark.parametrize("exc_cls,code", CASES)
    def test_app_exceptions_use_envelope(
        self, client: TestClient, exc_cls: type[AppException], code: ErrorCode
    ) -> None:
        r = client.get(f"/raise/{int(code)}")
        assert r.status_code == ErrorConfig.status(code)
        assert r.json() == {
            "success": False,
            "message": ErrorConfig.message(code),
            "error_code": int(code),
            "data": {"why": "test"},
        }

    def test_unknown_route(self, client: TestClient) -> None:
        r = client.get("/nope")
        assert r.status_code == 404
        body = r.json()
        assert body["success"] is False
        assert body["error_code"] == int(ErrorCode.NOT_FOUND)
        assert body["data"] == {}

    def test_wrong_method(self, client: TestClient) -> None:
        r = client.post("/crash")
        assert r.status_code == 405
        assert r.json()["error_code"] == int(ErrorCode.METHOD_NOT_ALLOWED)

    def test_request_validation(self, client: TestClient) -> None:
        r = client.get("/needs-int?n=abc")
        assert r.status_code == 422
        body = r.json()
        assert body["error_code"] == int(ErrorCode.VALIDATION)
        assert body["data"][0]["loc"] == ["query", "n"]

    def test_unexpected_error_is_generic(self, client: TestClient) -> None:
        r = client.get("/crash")
        assert r.status_code == 500
        assert r.json()["error_code"] == int(ErrorCode.INTERNAL)
        assert "secret internals" not in r.text
