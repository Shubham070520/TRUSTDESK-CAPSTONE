import json
from uuid import uuid4

import pytest

from app.common.exceptions import NotFoundError, ValidationError
from app.common.logger import Logger
from app.config import Config, ErrorCode
from app.handler.base import BaseHandler


class TestBaseHandler:
    @pytest.fixture()
    def handler(self) -> BaseHandler:
        return BaseHandler(Logger("test"))

    def test_return_json_success_shape(self, handler: BaseHandler) -> None:
        r = handler.return_json(True, "done", {"a": 1})
        assert r.status_code == 200
        assert json.loads(r.body) == {"success": True, "message": "done", "data": {"a": 1}}

    def test_return_json_error_shape(self, handler: BaseHandler) -> None:
        r = handler.return_json(False, "bad", error_code=1001, status_code=422)
        assert r.status_code == 422
        assert json.loads(r.body) == {
            "success": False,
            "message": "bad",
            "error_code": 1001,
            "data": {},
        }

    def test_execute_success(self, handler: BaseHandler) -> None:
        r = handler.execute(lambda: {"x": 1}, "ok", status_code=201)
        assert r.status_code == 201
        assert json.loads(r.body)["data"] == {"x": 1}

    def test_execute_catches_app_exception(self, handler: BaseHandler) -> None:
        def fail() -> None:
            raise NotFoundError(details={"id": "z"})

        r = handler.execute(fail, "ok")
        body = json.loads(r.body)
        assert r.status_code == 404
        assert body["success"] is False
        assert body["error_code"] == int(ErrorCode.NOT_FOUND)
        assert body["data"] == {"id": "z"}

    def test_execute_maps_unexpected_to_generic_500(self, handler: BaseHandler) -> None:
        def crash() -> None:
            raise RuntimeError("secret internals")

        r = handler.execute(crash, "ok")
        assert r.status_code == 500
        assert json.loads(r.body)["error_code"] == int(ErrorCode.INTERNAL)
        assert b"secret internals" not in r.body

    def test_validate_uuid(self, handler: BaseHandler) -> None:
        value = str(uuid4())
        assert handler.validate_uuid(value) == value
        for bad in ("nope", "", "123", str(uuid4()) + "x"):
            with pytest.raises(ValidationError):
                handler.validate_uuid(bad)

    def test_validate_pagination(self, handler: BaseHandler) -> None:
        assert handler.validate_pagination(1, 20) == (1, 20)
        assert handler.validate_pagination(3, Config.MAX_PAGE_SIZE) == (3, Config.MAX_PAGE_SIZE)
        for page, size in ((0, 20), (1, 0), (1, Config.MAX_PAGE_SIZE + 1), (-1, 5)):
            with pytest.raises(ValidationError):
                handler.validate_pagination(page, size)
