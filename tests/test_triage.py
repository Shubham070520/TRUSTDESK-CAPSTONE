import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app import Application
from app.common.enums import Sentiment, TicketCategory, TicketPriority
from app.common.exceptions import ProviderError
from app.common.mock_adapter import RuleBasedMockAdapter
from app.common.model_adapter import (
    CustomerContext,
    ItemContext,
    OrderContext,
    TicketContext,
    TriageResult,
)
from app.config import Config, ErrorCode
from app.models.agent_run import AgentRun
from app.models.eval_case import EvalCase
from app.models.ticket_label import TicketLabel
from tests.base import ApiTestCase, SeededApiTestCase

TICKET_IDS = [f"tkt_900{n}" for n in range(1, 9)]
CATEGORIES = [
    "refund",
    "shipping",
    "refund",
    "warranty",
    "account_security",
    "general",
    "account_security",
    "billing",
]
PRIORITIES = ["medium", "high", "low", "urgent", "high", "medium", "high", "high"]
ESCALATED = {"tkt_9004", "tkt_9005", "tkt_9006", "tkt_9007"}
FLAGGED = {"tkt_9005", "tkt_9006", "tkt_9007"}
UNKNOWN_RUN = "7f3c2c9e-5b1a-4a57-9c3a-0d4e1f2a3b4c"


def make_ticket(
    subject: str = "Question",
    body: str = "Hello",
    opened_at: str = "2026-06-28T10:00:00+05:30",
    return_until: str | None = "2026-07-01",
    final_sale: bool = False,
    with_order: bool = True,
) -> TicketContext:
    item = ItemContext("SKU-1", "Thing", 1, "audio", final_sale)
    order = OrderContext(
        "ord_1", "delivered", "2026-06-24", return_until, "TRK", 100.0, "INR", "paid", (item,)
    )
    customer = CustomerContext("cus_1", "Test Customer", "standard", True)
    return TicketContext(
        "tkt_1", "email", subject, body, opened_at, customer, order if with_order else None
    )


def fixed_result(_self: Any, _ticket: TicketContext) -> TriageResult:
    return TriageResult(
        TicketCategory.GENERAL, TicketPriority.LOW, Sentiment.NEUTRAL, False, "Model says fine."
    )


class TestMockRules:
    adapter = RuleBasedMockAdapter()

    @pytest.mark.parametrize(
        "body",
        ["My charger is overheating", "There is a burning smell", "I can see exposed wires"],
    )
    def test_safety_hazards_are_urgent_and_escalated(self, body: str) -> None:
        result = self.adapter.triage(make_ticket(body=body))
        assert result.category is TicketCategory.WARRANTY
        assert result.priority is TicketPriority.URGENT
        assert result.should_escalate is True
        assert result.sentiment is Sentiment.WORRIED

    @pytest.mark.parametrize(
        ("opened_at", "category"),
        [
            ("2026-07-01T23:00:00+05:30", TicketCategory.REFUND),
            ("2026-07-02T00:30:00+05:30", TicketCategory.WARRANTY),
        ],
    )
    def test_defect_category_follows_the_return_window(
        self, opened_at: str, category: TicketCategory
    ) -> None:
        ticket = make_ticket(body="It stopped working", opened_at=opened_at)
        assert self.adapter.triage(ticket).category is category

    def test_damage_outranks_shipping_wording(self) -> None:
        ticket = make_ticket(body="Tracking says delivered but the box arrived damaged")
        assert self.adapter.triage(ticket).category is TicketCategory.REFUND

    def test_stale_tracking_without_urgent_need_is_medium(self) -> None:
        result = self.adapter.triage(make_ticket(body="Tracking shows no movement"))
        assert result.category is TicketCategory.SHIPPING
        assert result.priority is TicketPriority.MEDIUM

    def test_final_sale_refund_is_low_even_inside_the_window(self) -> None:
        result = self.adapter.triage(make_ticket(body="Please refund this", final_sale=True))
        assert result.priority is TicketPriority.LOW

    def test_ordinary_refund_inside_the_window_is_medium(self) -> None:
        result = self.adapter.triage(make_ticket(body="Please refund this"))
        assert result.priority is TicketPriority.MEDIUM

    def test_late_refund_is_low(self) -> None:
        ticket = make_ticket(body="Please refund this", opened_at="2026-08-01T10:00:00+05:30")
        assert self.adapter.triage(ticket).priority is TicketPriority.LOW

    def test_refund_without_an_order_is_medium(self) -> None:
        ticket = make_ticket(body="Please refund this", with_order=False)
        assert self.adapter.triage(ticket).priority is TicketPriority.MEDIUM

    def test_malformed_timestamp_counts_as_outside_the_window(self) -> None:
        ticket = make_ticket(body="It stopped working", opened_at="not-a-date")
        assert self.adapter.triage(ticket).category is TicketCategory.WARRANTY

    def test_unmatched_ticket_is_general_and_neutral(self) -> None:
        result = self.adapter.triage(make_ticket(subject="Store hours", body="When do you open?"))
        assert result.category is TicketCategory.GENERAL
        assert result.priority is TicketPriority.MEDIUM
        assert result.sentiment is Sentiment.NEUTRAL
        assert result.should_escalate is False

    def test_angry_wording(self) -> None:
        result = self.adapter.triage(make_ticket(body="This is unacceptable"))
        assert result.sentiment is Sentiment.ANGRY

    def test_reason_never_quotes_the_customer(self) -> None:
        result = self.adapter.triage(make_ticket(body="Refund me, my code is zebra-4471"))
        assert "zebra-4471" not in result.reason_summary

    def test_is_deterministic(self) -> None:
        ticket = make_ticket(body="The battery is swelling")
        assert self.adapter.triage(ticket) == self.adapter.triage(ticket)


class TestTriageApi(SeededApiTestCase):
    def _triage(self, client: TestClient, auth: dict[str, str], ticket_id: str) -> dict[str, Any]:
        response = client.post(f"/tickets/{ticket_id}/triage", headers=auth)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def _stored(self, client: TestClient, auth: dict[str, str], ticket_id: str) -> dict[str, Any]:
        return client.get(f"/tickets/{ticket_id}", headers=auth).json()["data"]["latest_triage"]

    @pytest.mark.parametrize(
        ("ticket_id", "category", "priority"), list(zip(TICKET_IDS, CATEGORIES, PRIORITIES))
    )
    def test_plan_expectations(
        self,
        client: TestClient,
        auth: dict[str, str],
        ticket_id: str,
        category: str,
        priority: str,
    ) -> None:
        data = self._triage(client, auth, ticket_id)
        assert data["category"] == category
        assert data["priority"] == priority
        assert data["should_escalate"] is (ticket_id in ESCALATED)
        assert data["guardrail_flagged"] is (ticket_id in FLAGGED)

    def test_matches_the_eval_cases_and_seed_sentiment(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        data_dir = Config.BASE_DIR / "data"
        lines = (data_dir / "eval_cases.jsonl").read_text(encoding="utf-8").splitlines()
        cases = [json.loads(line) for line in lines if line.strip()]
        tickets = json.loads((data_dir / "tickets.json").read_text(encoding="utf-8"))
        sentiments = {t["ticket_id"]: t["expected_sentiment"] for t in tickets}
        assert len(cases) == 8
        for case in cases:
            ticket_id, expected = case["ticket_id"], case["expected"]
            data = self._triage(client, auth, ticket_id)
            assert data["category"] == expected["category"], ticket_id
            assert data["priority"] == expected["priority"], ticket_id
            assert data["should_escalate"] is expected["should_escalate"], ticket_id
            assert data["sentiment"] == sentiments[ticket_id], ticket_id

    def test_response_has_the_contract_fields(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        body = client.post("/tickets/tkt_9001/triage", headers=auth).json()
        assert body["success"] is True
        assert body["message"] == "Ticket triaged"
        assert set(body["data"]) == {
            "ticket_id",
            "category",
            "priority",
            "sentiment",
            "should_escalate",
            "reason_summary",
            "run_id",
            "guardrail_flagged",
            "guardrail_reasons",
        }
        assert body["data"]["ticket_id"] == "tkt_9001"
        assert body["data"]["reason_summary"]

    def test_result_is_stored_on_the_ticket(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        data = self._triage(client, auth, "tkt_9004")
        assert self._stored(client, auth, "tkt_9004") == {
            "category": "warranty",
            "priority": "urgent",
            "sentiment": "worried",
            "should_escalate": True,
            "reason_summary": data["reason_summary"],
            "run_id": data["run_id"],
        }

    def test_triage_again_makes_a_new_run_and_keeps_the_latest(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        first = self._triage(client, auth, "tkt_9001")["run_id"]
        second = self._triage(client, auth, "tkt_9001")["run_id"]
        assert first != second
        assert self._stored(client, auth, "tkt_9001")["run_id"] == second
        assert client.get(f"/agent-runs/{first}", headers=auth).status_code == 200

    def test_does_not_read_the_expectation_tables(
        self, client: TestClient, auth: dict[str, str], application: Application
    ) -> None:
        with application.database.session_scope() as db:
            db.execute(delete(TicketLabel))
            db.execute(delete(EvalCase))
            db.commit()
        for ticket_id, category in zip(TICKET_IDS, CATEGORIES):
            assert self._triage(client, auth, ticket_id)["category"] == category

    def test_guardrail_flag_overrides_the_model(
        self, client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(RuleBasedMockAdapter, "triage", fixed_result)
        data = self._triage(client, auth, "tkt_9006")
        assert data["should_escalate"] is True
        assert data["guardrail_flagged"] is True
        assert data["guardrail_reasons"]
        assert "guardrail flagged" in data["reason_summary"]
        assert data["guardrail_reasons"][0] in data["reason_summary"]
        assert self._stored(client, auth, "tkt_9006")["should_escalate"] is True

    def test_clean_ticket_keeps_the_model_decision(
        self, client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(RuleBasedMockAdapter, "triage", fixed_result)
        data = self._triage(client, auth, "tkt_9001")
        assert data["should_escalate"] is False
        assert data["reason_summary"] == "Model says fine."
        assert data["guardrail_reasons"] == []

    def test_requires_a_token(self, client: TestClient) -> None:
        assert client.post("/tickets/tkt_9001/triage").status_code == 401

    def test_unknown_ticket_is_404_and_writes_no_run(
        self, client: TestClient, auth: dict[str, str], application: Application
    ) -> None:
        response = client.post("/tickets/tkt_0000/triage", headers=auth)
        assert response.status_code == 404
        assert response.json()["error_code"] == int(ErrorCode.NOT_FOUND)
        with application.database.session_scope() as db:
            assert db.execute(select(func.count(AgentRun.id))).scalar_one() == 0

    def test_bad_ticket_id_is_422(self, client: TestClient, auth: dict[str, str]) -> None:
        assert client.post("/tickets/bad%20id/triage", headers=auth).status_code == 422

    def test_provider_failure_leaves_the_ticket_and_records_a_failed_run(
        self, client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._triage(client, auth, "tkt_9006")
        before = self._stored(client, auth, "tkt_9006")

        def fail(_self: Any, _ticket: TicketContext) -> TriageResult:
            raise ProviderError(details={"provider": "mock", "reason": "timeout"})

        monkeypatch.setattr(RuleBasedMockAdapter, "triage", fail)
        response = client.post("/tickets/tkt_9006/triage", headers=auth)
        assert response.status_code == 504
        body = response.json()
        assert body["error_code"] == int(ErrorCode.PROVIDER)
        assert body["data"]["reason"] == "timeout"

        trace = client.get(f"/agent-runs/{body['data']['run_id']}", headers=auth).json()["data"]
        assert trace["status"] == "failed"
        assert trace["guardrail_results"]["input"]["flagged"] is True
        assert self._stored(client, auth, "tkt_9006") == before

    def test_model_call_holds_no_database_connection(
        self,
        client: TestClient,
        auth: dict[str, str],
        application: Application,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seen: list[int] = []

        def record(self: Any, ticket: TicketContext) -> TriageResult:
            seen.append(application.database.engine.pool.checkedout())
            return fixed_result(self, ticket)

        monkeypatch.setattr(RuleBasedMockAdapter, "triage", record)
        self._triage(client, auth, "tkt_9001")
        assert seen == [0]

    def test_slow_calls_run_at_the_same_time(
        self, application: Application, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        barrier = Barrier(2, timeout=10)

        def wait_for_the_other(self: Any, ticket: TicketContext) -> TriageResult:
            barrier.wait()  # breaks, and the request fails, unless both calls are in flight
            return fixed_result(self, ticket)

        monkeypatch.setattr(RuleBasedMockAdapter, "triage", wait_for_the_other)
        # The context manager gives one shared event loop, as a real server has.
        with TestClient(application.create_app(), raise_server_exceptions=False) as shared:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda ticket: shared.post(f"/tickets/{ticket}/triage", headers=auth),
                        ["tkt_9001", "tkt_9002"],
                    )
                )
        assert [r.status_code for r in responses] == [200, 200]

    def test_context_given_to_the_model_has_no_labels_or_email(
        self, client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contexts: list[TicketContext] = []

        def capture(self: Any, ticket: TicketContext) -> TriageResult:
            contexts.append(ticket)
            return fixed_result(self, ticket)

        monkeypatch.setattr(RuleBasedMockAdapter, "triage", capture)
        self._triage(client, auth, "tkt_9001")
        rendered = repr(contexts[0])
        assert "aisha.rao@example.com" not in rendered
        assert "expected" not in rendered
        assert contexts[0].customer.customer_id == "cus_1001"
        assert contexts[0].order is not None
        assert contexts[0].order.eligible_return_until == "2026-07-01"
        assert contexts[0].order.items[0].sku == "BG-AIRPODS-01"


class TestAgentRunApi(SeededApiTestCase):
    def test_returns_the_trace(self, client: TestClient, auth: dict[str, str]) -> None:
        run_id = client.post("/tickets/tkt_9006/triage", headers=auth).json()["data"]["run_id"]
        response = client.get(f"/agent-runs/{run_id}", headers=auth)
        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Agent run retrieved"
        data = body["data"]
        assert data["run_id"] == run_id
        assert data["ticket_id"] == "tkt_9006"
        assert data["run_type"] == "triage"
        assert data["status"] == "completed"
        assert data["retrieved_doc_ids"] == []
        assert data["tool_calls"] == []
        assert data["created_at"]
        guardrail = data["guardrail_results"]["input"]
        assert guardrail["flagged"] is True
        assert guardrail["reasons"]
        assert guardrail["evidence"]

    def test_clean_ticket_trace_shows_the_scan_passed(
        self, client: TestClient, auth: dict[str, str]
    ) -> None:
        run_id = client.post("/tickets/tkt_9001/triage", headers=auth).json()["data"]["run_id"]
        data = client.get(f"/agent-runs/{run_id}", headers=auth).json()["data"]
        assert data["guardrail_results"] == {
            "input": {"flagged": False, "reasons": [], "evidence": {}}
        }

    def test_requires_a_token(self, client: TestClient) -> None:
        assert client.get(f"/agent-runs/{UNKNOWN_RUN}").status_code == 401

    def test_unknown_run_is_404(self, client: TestClient, auth: dict[str, str]) -> None:
        response = client.get(f"/agent-runs/{UNKNOWN_RUN}", headers=auth)
        assert response.status_code == 404
        assert response.json()["error_code"] == int(ErrorCode.NOT_FOUND)

    def test_malformed_run_id_is_422(self, client: TestClient, auth: dict[str, str]) -> None:
        assert client.get("/agent-runs/not-a-uuid", headers=auth).status_code == 422


class TestTriageOnEmptyDatabase(ApiTestCase):
    def test_unknown_ticket_on_a_fresh_server(
        self, application: Application, auth: dict[str, str]
    ) -> None:
        with TestClient(application.create_app()) as client:
            assert client.post("/tickets/tkt_9001/triage", headers=auth).status_code == 404
