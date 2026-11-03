import json
from typing import Any

from fastapi.testclient import TestClient

from app import Application
from app.config import ErrorCode
from app.models import Draft, Ticket
from sqlalchemy import select
from tests.base import SeededApiTestCase


class TestListTickets(SeededApiTestCase):
    def test_returns_every_seeded_ticket(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        r = client.get("/tickets", headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert data["total"] == 8
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 1
        assert [t["ticket_id"] for t in data["items"]] == [f"tkt_90{n:02d}" for n in range(1, 9)]

    def test_item_shape_uses_source_created_at(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        item = client.get("/tickets", headers=auth).json()["data"]["items"][0]
        assert item["created_at"] == "2026-06-28T10:15:00+05:30"
        assert item["subject"] == "Received damaged earbuds"
        assert item["status"] == "open"
        assert item["triage"] is None
        assert "opened_at" not in item

    def test_pagination(self, client: TestClient, auth: dict[str, str]) -> None:
        last = client.get("/tickets?page=3&page_size=3", headers=auth).json()["data"]
        assert [t["ticket_id"] for t in last["items"]] == ["tkt_9007", "tkt_9008"]
        assert (last["total"], last["total_pages"]) == (8, 3)
        beyond = client.get("/tickets?page=9&page_size=3", headers=auth).json()["data"]
        assert beyond["items"] == []
        assert beyond["total"] == 8

    def test_status_filter(self, client: TestClient, auth: dict[str, str]) -> None:
        assert client.get("/tickets?status=open", headers=auth).json()["data"]["total"] == 8
        closed = client.get("/tickets?status=closed", headers=auth).json()["data"]
        assert closed["total"] == 0
        assert closed["total_pages"] == 0

    def test_bad_pagination_is_validation_error(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        for query in ("page=0", "page_size=0", "page_size=101", "page=-1"):
            r = client.get(f"/tickets?{query}", headers=auth)
            assert r.status_code == 422, query
            assert r.json()["error_code"] == int(ErrorCode.VALIDATION)

    def test_non_numeric_pagination_is_validation_error(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        r = client.get("/tickets?page=abc", headers=auth)
        assert r.status_code == 422
        assert r.json()["error_code"] == int(ErrorCode.VALIDATION)

    def test_malformed_status_is_validation_error(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        assert client.get("/tickets?status=a%20b", headers=auth).status_code == 422
        assert client.get("/tickets?status=%27%3B--", headers=auth).status_code == 422

    def test_list_shows_stored_triage(
        self, client: TestClient, auth: dict[str, str], application: Application
    ) -> None:
        with application.database.session_scope() as db:
            ticket = db.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9001")).scalar_one()
            ticket.triage_category = "refund"
            ticket.triage_priority = "medium"
            ticket.triage_sentiment = "frustrated"
            ticket.triage_escalate = False
            ticket.triage_reason = "Damaged item within window"
            ticket.triage_run_id = "run-1"
            db.commit()
        item = client.get("/tickets", headers=auth).json()["data"]["items"][0]
        assert item["triage"] == {
            "category": "refund",
            "priority": "medium",
            "sentiment": "frustrated",
            "should_escalate": False,
            "reason_summary": "Damaged item within window",
            "run_id": "run-1",
        }


class TestTicketDetail(SeededApiTestCase):
    def test_includes_customer_and_order(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        r = client.get("/tickets/tkt_9001", headers=auth)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["ticket"]["ticket_id"] == "tkt_9001"
        assert data["customer"]["customer_id"] == "cus_1001"
        assert data["customer"]["tier"] == "gold"
        assert data["customer"]["created_at"] == "2024-05-14"
        assert data["order"]["order_id"] == "ord_5001"
        assert data["order"]["eligible_return_until"] == "2026-07-01"
        assert data["order"]["delivered_at"] == "2026-06-24"
        assert data["order"]["items"][0]["sku"] == "BG-AIRPODS-01"
        assert data["latest_triage"] is None
        assert data["latest_draft"] is None

    def test_ticket_text_and_timestamp_unchanged(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        data = client.get("/tickets/tkt_9001", headers=auth).json()["data"]
        assert data["ticket"]["created_at"] == "2026-06-28T10:15:00+05:30"
        assert data["ticket"]["body"].startswith("Hi, my BlueBuds Air arrived")

    def test_every_seeded_ticket_resolves_with_context(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        for n in range(1, 9):
            data = client.get(f"/tickets/tkt_90{n:02d}", headers=auth).json()["data"]
            assert data["customer"]["customer_id"]
            assert data["order"]["order_id"]

    def test_unverified_customer_visible_for_security_cases(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        data = client.get("/tickets/tkt_9005", headers=auth).json()["data"]
        assert data["customer"]["verified"] is False

    def test_unknown_ticket_is_404(self, client: TestClient, auth: dict[str, str]) -> None:
        r = client.get("/tickets/tkt_0000", headers=auth)
        assert r.status_code == 404
        assert r.json() == {
            "success": False,
            "message": "Resource not found",
            "error_code": int(ErrorCode.NOT_FOUND),
            "data": {"ticket_id": "tkt_0000"},
        }

    def test_malformed_ticket_id_is_422(self, client: TestClient, auth: dict[str, str]) -> None:
        for bad in ("bad%20id", "a%27b", "x" * 80):
            r = client.get(f"/tickets/{bad}", headers=auth)
            assert r.status_code == 422, bad
            assert r.json()["error_code"] == int(ErrorCode.VALIDATION)

    def test_returns_latest_draft_and_triage(
        self, client: TestClient, auth: dict[str, str], application: Application
    ) -> None:
        with application.database.session_scope() as db:
            ticket = db.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9001")).scalar_one()
            ticket.triage_category = "refund"
            ticket.triage_priority = "medium"
            db.add(Draft(ticket_id="tkt_9001", body="first", citations=["KB-REFUND-001"]))
            db.flush()
            newest = Draft(ticket_id="tkt_9001", body="second", citations=["KB-REFUND-001"])
            db.add(newest)
            db.commit()
            newest_uuid = newest.uuid
        data = client.get("/tickets/tkt_9001", headers=auth).json()["data"]
        assert data["latest_draft"]["body"] == "second"
        assert data["latest_draft"]["draft_id"] == newest_uuid
        assert data["latest_draft"]["status"] == "generated"
        assert data["latest_draft"]["citations"] == ["KB-REFUND-001"]
        assert data["latest_triage"]["category"] == "refund"

    def test_soft_deleted_ticket_is_hidden(
        self, client: TestClient, auth: dict[str, str], application: Application
    ) -> None:
        with application.database.session_scope() as db:
            ticket = db.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9002")).scalar_one()
            ticket.is_deleted = True
            db.commit()
        assert client.get("/tickets/tkt_9002", headers=auth).status_code == 404
        assert client.get("/tickets", headers=auth).json()["data"]["total"] == 7


class TestNoLabelLeak(SeededApiTestCase):
    """Seed expectations are for evaluation only and must never reach a client."""

    FORBIDDEN = ("expected_", "expected_category", "expected_priority", "expected_actions")

    @staticmethod
    def _keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            found = set(value)
            for item in value.values():
                found |= TestNoLabelLeak._keys(item)
            return found
        if isinstance(value, list):
            found: set[str] = set()
            for item in value:
                found |= TestNoLabelLeak._keys(item)
            return found
        return set()

    def test_list_and_detail_have_no_expected_fields(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        bodies = [client.get("/tickets", headers=auth).json()]
        bodies += [client.get(f"/tickets/tkt_90{n:02d}", headers=auth).json() for n in range(1, 9)]
        for body in bodies:
            assert not [k for k in self._keys(body) if k.startswith("expected")]
            assert "expected_" not in json.dumps(body)
