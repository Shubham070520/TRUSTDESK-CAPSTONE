import pytest
from fastapi.testclient import TestClient

from app.config import ErrorCode
from tests.base import SeededApiTestCase

PROTECTED = [
    ("GET", "/tickets"),
    ("GET", "/tickets/tkt_9001"),
    ("GET", "/documents/search?q=refund"),
    ("POST", "/documents/ingest"),
]


class TestAuth(SeededApiTestCase):
    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_missing_token_is_401_envelope(
        self, client: TestClient, method: str, path: str
    ) -> None:
        r = client.request(method, path, json={"documents": []} if method == "POST" else None)
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert r.json() == {
            "success": False,
            "message": "Authentication failed",
            "error_code": int(ErrorCode.AUTHENTICATION),
            "data": {},
        }

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_wrong_token_is_401(self, client: TestClient, method: str, path: str) -> None:
        r = client.request(
            method,
            path,
            headers={"Authorization": "Bearer nope"},
            json={"documents": []} if method == "POST" else None,
        )
        assert r.status_code == 401

    @pytest.mark.parametrize(
        "header", ["Basic dGVzdC10b2tlbg==", "test-token", "Bearer", "Bearer  ", "Token test-token"]
    )
    def test_malformed_authorization_is_401(self, client: TestClient, header: str) -> None:
        assert client.get("/tickets", headers={"Authorization": header}).status_code == 401

    def test_token_is_case_sensitive(self, client: TestClient) -> None:
        r = client.get("/tickets", headers={"Authorization": "Bearer TEST-TOKEN"})
        assert r.status_code == 401

    def test_valid_token_is_accepted(self, client: TestClient, auth: dict[str, str]) -> None:
        assert client.get("/tickets", headers=auth).status_code == 200

    def test_scheme_name_is_case_insensitive(self, client: TestClient) -> None:
        r = client.get("/tickets", headers={"Authorization": "bearer test-token"})
        assert r.status_code == 200

    def test_health_stays_open(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200

    def test_auth_runs_before_validation(self, client: TestClient) -> None:
        # A bad query without a token must not leak validation details.
        r = client.get("/tickets?page=0")
        assert r.status_code == 401
