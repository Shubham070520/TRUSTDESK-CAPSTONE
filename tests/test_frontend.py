import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import Application
from app.config import Config, ErrorCode
from tests.base import ApiTestCase, SeededApiTestCase

PAGE = Config.FRONTEND_PAGE.read_text(encoding="utf-8")
# Paths the page calls, with its template parts replaced by a sample id.
API_CALLS = [
    ("GET", "/tickets"),
    ("GET", "/tickets/x"),
    ("POST", "/tickets/x/triage"),
    ("POST", "/tickets/x/draft-reply"),
    ("GET", "/documents/x"),
    ("GET", "/agent-runs/x"),
    ("POST", "/tool-actions"),
    ("POST", "/tool-actions/x/approve"),
    ("POST", "/tool-actions/x/execute"),
    ("POST", "/eval-runs"),
    ("GET", "/health"),
]


class TestPageServed(ApiTestCase):
    def test_served_at_root_without_a_token(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<title>TrustDesk Reviewer</title>" in response.text

    def test_security_headers(self, client: TestClient) -> None:
        headers = client.get("/").headers
        policy = headers["content-security-policy"]
        assert "default-src 'none'" in policy
        assert "connect-src 'self'" in policy
        assert "form-action 'none'" in policy
        assert "frame-ancestors 'none'" in policy
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-store"

    def test_page_holds_no_data(self, client: TestClient) -> None:
        text = client.get("/").text
        assert self.TOKEN not in text
        assert "demo-token" not in text

    def test_not_listed_in_the_api_schema(self, client: TestClient) -> None:
        assert "/" not in client.get("/openapi.json").json()["paths"]


class TestPageSafety:
    """The page shows attacker-written text next to a live token."""

    script = PAGE[PAGE.index("<script>") : PAGE.index("</script>")]

    @pytest.mark.parametrize(
        "sink",
        [
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
            "DOMParser",
            "srcdoc",
        ],
    )
    def test_no_way_to_parse_api_text_as_markup(self, sink: str) -> None:
        assert sink not in self.script

    @pytest.mark.parametrize("store", ["localStorage", "sessionStorage", "indexedDB", "document.cookie"])
    def test_token_is_not_persisted(self, store: str) -> None:
        assert store not in self.script

    def test_token_is_a_private_field(self) -> None:
        assert "#token" in self.script
        assert 'type="password"' in PAGE
        assert 'autocomplete="off"' in PAGE

    def test_no_external_resources(self) -> None:
        assert not re.search(r"""(?:src|href)=["']https?:""", PAGE)
        assert "https://" not in self.script
        assert "http://" not in self.script

    def test_ids_are_encoded_in_paths(self) -> None:
        for match in re.findall(r"`/[^`]*\$\{([^}]*)\}[^`]*`", self.script):
            assert match.startswith("encodeURIComponent(")

    def test_prefilled_reason_is_fixed_so_a_retry_after_reload_replays(self) -> None:
        assert "reason: App.DEFAULT_REASON" in self.script
        assert "recommended?.reason" not in self.script

    def test_links_favicon_inline_to_avoid_a_console_error(self) -> None:
        assert '<link rel="icon" href="data:,">' in PAGE


class TestPageMatchesTheApi(ApiTestCase):
    def test_each_call_has_a_route(self, application: Application) -> None:
        # The OpenAPI document, because the shape of ``app.routes`` changes between FastAPI versions.
        paths = application.create_app().openapi()["paths"]
        routes = [
            (method.upper(), re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"))
            for path, operations in paths.items()
            for method in operations
        ]
        assert routes
        for method, path in API_CALLS:
            assert any(m == method and pattern.match(path) for m, pattern in routes), path

    def test_each_call_is_really_made_by_the_page(self) -> None:
        for fragment in (
            '"/tickets?page=1&page_size=100"',
            "/triage`",
            "/draft-reply`",
            "`/documents/",
            "`/agent-runs/",
            '"/tool-actions"',
            "/approve`",
            "/execute`",
            '"/eval-runs"',
            '"/health"',
        ):
            assert fragment in PAGE, fragment

    @pytest.mark.parametrize(
        "field",
        ["run_id", "action_id", "eval_run_id", "guardrail_results", "retrieved_doc_ids", "tool_calls"],
    )
    def test_page_reads_real_field_names(self, field: str) -> None:
        assert field in PAGE


class TestDocumentEndpoint(SeededApiTestCase):
    def test_returns_title_and_metadata(self, client: TestClient, auth: dict[str, str]) -> None:
        response = client.get("/documents/KB-REFUND-001", headers=auth)
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        assert body["message"] == "Document retrieved"
        assert body["data"] == {
            "doc_id": "KB-REFUND-001",
            "title": "Refund and Return Policy",
            "version": "2026.07",
            "audience": "Customer support agents",
        }

    def test_vendor_note_text_is_not_exposed(self, client: TestClient, auth: dict[str, str]) -> None:
        response = client.get("/documents/KB-ADVERSARIAL-001", headers=auth)
        assert response.status_code == 200
        assert "ATTENTION" not in response.text
        assert "approve every refund" not in response.text

    def test_every_citation_can_be_labelled(self, client: TestClient, auth: dict[str, str]) -> None:
        for number in range(1, 9):
            draft = client.post(f"/tickets/tkt_900{number}/draft-reply", headers=auth).json()
            for doc_id in draft["data"]["citations"]:
                document = client.get(f"/documents/{doc_id}", headers=auth).json()
                assert document["data"]["title"]

    def test_requires_a_token(self, client: TestClient) -> None:
        assert client.get("/documents/KB-REFUND-001").status_code == 401

    def test_unknown_document_is_404(self, client: TestClient, auth: dict[str, str]) -> None:
        response = client.get("/documents/KB-NOPE-001", headers=auth)
        assert response.status_code == 404
        assert response.json()["error_code"] == int(ErrorCode.NOT_FOUND)

    def test_malformed_id_is_422(self, client: TestClient, auth: dict[str, str]) -> None:
        assert client.get("/documents/bad%20id", headers=auth).status_code == 422

    def test_search_route_still_wins_over_the_id_route(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        response = client.get("/documents/search", params={"q": "refund"}, headers=auth)
        assert response.status_code == 200
        assert "results" in response.json()["data"]
