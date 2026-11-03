from pathlib import Path

from fastapi.testclient import TestClient

from app import Application
from app.config import Config, ErrorCode
from tests.base import ApiTestCase


class TestHealthEndpoint(ApiTestCase):
    def test_health_is_open_and_ok(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {
            "success": True,
            "message": "Service is healthy",
            "data": {"status": "ok", "database": "ok"},
        }

    def test_health_needs_no_token(self, client: TestClient) -> None:
        assert client.get("/health", headers={}).status_code == 200

    def test_unknown_route_uses_envelope(self, client: TestClient) -> None:
        r = client.get("/nope")
        assert r.status_code == 404
        assert r.json()["error_code"] == int(ErrorCode.NOT_FOUND)

    def test_openapi_lists_health(self, client: TestClient) -> None:
        assert "/health" in client.get("/openapi.json").json()["paths"]

    def test_database_failure_returns_503_envelope(self, tmp_path: Path) -> None:
        config = Config(
            token="t",
            db_path=str(tmp_path / "missing_dir" / "x.db"),
            model_provider="mock",
        )
        application = Application(config)
        try:
            client = TestClient(application.create_app(), raise_server_exceptions=False)
            r = client.get("/health")
            assert r.status_code == 503
            body = r.json()
            assert body["success"] is False
            assert body["error_code"] == int(ErrorCode.DATABASE)
        finally:
            application.database.dispose()


class TestSqliteCapabilities:
    def test_fts5_available(self, tmp_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "fts.db"))
        try:
            conn.execute("create virtual table t using fts5(a)")
            conn.execute("insert into t(a) values ('damaged item replacement')")
            count = conn.execute("select count(*) from t where t match 'damaged'").fetchone()[0]
            assert count == 1
        finally:
            conn.close()
