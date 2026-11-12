import json
from datetime import date
from typing import Any, Iterator

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app import Application
from app.common.data_reader import DataFileReader
from app.common.document_parser import KnowledgeDocumentParser
from app.common.exceptions import ValidationError
from app.config import Config
from app.helper.document import DocumentHelper
from app.helper.schema import SchemaHelper
from app.helper.seed import SeedHelper
from app.models import (
    Customer,
    Document,
    EvalCase,
    Order,
    Ticket,
    TicketLabel,
    Tool,
)
from app.models.base import TableNames
from tests.base import ApiTestCase


class SeedTestCase(ApiTestCase):
    """Fixtures that give each test a fresh database with the real data files."""

    @pytest.fixture()
    def session(self, application: Application) -> Iterator[Session]:
        with application.database.session_scope() as db:
            SchemaHelper(db).init_schema()
            yield db

    @pytest.fixture()
    def seeder(self, session: Session) -> SeedHelper:
        return SeedHelper(
            session,
            DataFileReader(Config.BASE_DIR, Config.DATA_DIR),
            KnowledgeDocumentParser(),
            DocumentHelper(session),
        )

    @staticmethod
    def source(name: str) -> Any:
        path = Config.DATA_DIR / name
        text_ = path.read_text(encoding="utf-8")
        if name.endswith(".jsonl"):
            return [json.loads(line) for line in text_.splitlines() if line.strip()]
        return json.loads(text_)


class TestSchema(SeedTestCase):
    def test_all_tables_created(self, session: Session) -> None:
        names = set(inspect(session.connection()).get_table_names())
        expected = {
            TableNames.of(n)
            for n in (
                "Customer", "Order", "Ticket", "TicketLabel", "EvalCase", "Document",
                "Tool", "Draft", "ToolActionRequest", "Approval", "ReplacementOrder",
                "AgentRun", "EvalRun",
            )
        }
        assert expected <= names
        assert TableNames.documents_fts() in names

    def test_init_schema_is_repeatable(self, session: Session) -> None:
        SchemaHelper(session).init_schema()
        SchemaHelper(session).init_schema()

    def test_tickets_table_has_no_expected_columns(self, session: Session) -> None:
        columns = {c["name"] for c in inspect(session.connection()).get_columns(TableNames.of("Ticket"))}
        assert not [c for c in columns if c.startswith("expected_")]

    def test_idempotency_key_is_unique_and_replacement_action_unique(
        self, session: Session
    ) -> None:
        inspector = inspect(session.connection())
        action_table = TableNames.of("ToolActionRequest")
        unique_cols = {
            col
            for idx in inspector.get_indexes(action_table)
            if idx["unique"]
            for col in idx["column_names"]
        }
        assert "idempotency_key" in unique_cols
        replacement_unique = [
            u["column_names"] for u in inspector.get_unique_constraints(TableNames.of("ReplacementOrder"))
        ]
        assert ["action_id"] in replacement_unique

    def test_foreign_keys_enforced(self, session: Session) -> None:
        assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


class TestSeed(SeedTestCase):
    def test_counts_match_source_files(self, seeder: SeedHelper) -> None:
        counts = seeder.seed_all()
        assert counts["customers"] == len(self.source("customers.json")) == 6
        assert counts["orders"] == len(self.source("orders.json")) == 6
        assert counts["tickets"] == len(self.source("tickets.json")) == 8
        assert counts["ticket_labels"] == 8
        assert counts["tools"] == len(self.source("tool_actions.json")) == 6
        assert counts["eval_cases"] == len(self.source("eval_cases.jsonl")) == 8
        assert counts["documents"] == 8
        assert counts["document_sections"] >= 8

    def test_seeding_twice_creates_no_duplicates(self, seeder: SeedHelper) -> None:
        first = seeder.seed_all()
        second = seeder.seed_all()
        assert first == second

    def test_kb_doc_ids_preserved(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        ids = set(session.execute(select(Document.doc_id)).scalars())
        assert {"KB-REFUND-001", "KB-ADVERSARIAL-001", "KB-SECURITY-001"} <= ids

    def test_document_fields_populated(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        doc = session.execute(select(Document).where(Document.doc_id == "KB-REFUND-001")).scalar_one()
        assert doc.title == "Refund and Return Policy"
        assert doc.version == "2026.07"
        assert doc.audience == "Customer support agents"
        assert doc.source_path == "data/knowledge_base/refund_policy.md"
        assert len(doc.checksum) == 64
        assert "\r" not in doc.content

    def test_ticket_timestamp_and_body_preserved_exactly(
        self, seeder: SeedHelper, session: Session
    ) -> None:
        seeder.seed_all()
        for row in self.source("tickets.json"):
            ticket = session.execute(select(Ticket).where(Ticket.ticket_id == row["ticket_id"])).scalar_one()
            assert ticket.opened_at == row["created_at"]
            assert ticket.body == row["body"]
            assert ticket.subject == row["subject"]
            assert ticket.order_id == row["order_id"]

    def test_order_dates_and_items(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        order = session.execute(select(Order).where(Order.order_id == "ord_5001")).scalar_one()
        assert order.eligible_return_until == date(2026, 7, 1)
        assert order.delivered_at == date(2026, 6, 24)
        assert order.items[0]["sku"] == "BG-AIRPODS-01"
        in_transit = session.execute(select(Order).where(Order.order_id == "ord_5002")).scalar_one()
        assert in_transit.delivered_at is None
        assert in_transit.eligible_return_until is None

    def test_customer_fields(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        customer = session.execute(select(Customer).where(Customer.customer_id == "cus_1003")).scalar_one()
        assert customer.verified is False
        assert customer.tags == ["account_review"]
        assert customer.customer_since == "2023-11-02"

    def test_labels_only_in_label_and_eval_tables(
        self, seeder: SeedHelper, session: Session
    ) -> None:
        seeder.seed_all()
        label = session.execute(select(TicketLabel).where(TicketLabel.ticket_id == "tkt_9004")).scalar_one()
        assert label.expected_category == "warranty"
        assert label.expected_priority == "urgent"
        assert label.expected_escalation is True
        case = session.execute(select(EvalCase).where(EvalCase.case_id == "eval_006")).scalar_one()
        assert case.expected["disallowed_actions"] == ["issue_coupon"]
        ticket = session.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9004")).scalar_one()
        assert ticket.triage_category is None
        assert ticket.triage_priority is None

    def test_tools_loaded_with_catalog_rules(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        tool = session.execute(select(Tool).where(Tool.tool_name == "create_replacement_order")).scalar_one()
        assert tool.requires_human_approval is True
        assert tool.allowed_categories == ["refund", "warranty"]
        assert tool.required_fields == ["order_id", "sku", "reason", "idempotency_key"]
        coupon = session.execute(select(Tool).where(Tool.tool_name == "issue_coupon")).scalar_one()
        assert coupon.max_amount_inr == 1000

    def test_reseed_keeps_triage_results(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        ticket = session.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9001")).scalar_one()
        ticket.triage_category = "refund"
        ticket.triage_priority = "medium"
        session.commit()
        seeder.seed_all()
        session.refresh(ticket)
        assert ticket.triage_category == "refund"
        assert ticket.triage_priority == "medium"

    def test_relationships_resolve(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        ticket = session.execute(select(Ticket).where(Ticket.ticket_id == "tkt_9001")).scalar_one()
        assert ticket.customer.customer_id == "cus_1001"
        assert ticket.order is not None and ticket.order.order_id == "ord_5001"

    def test_no_foreign_key_violations(self, seeder: SeedHelper, session: Session) -> None:
        seeder.seed_all()
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    def test_search_index_finds_policy_sections(
        self, seeder: SeedHelper, session: Session
    ) -> None:
        seeder.seed_all()
        fts = TableNames.documents_fts()
        rows = session.execute(
            text(f"SELECT doc_id FROM {fts} WHERE {fts} MATCH :q ORDER BY rank LIMIT 1"),
            {"q": "damaged replacement"},
        ).fetchall()
        assert rows[0][0] == "KB-REFUND-001"

    def test_reindex_does_not_duplicate_sections(
        self, seeder: SeedHelper, session: Session
    ) -> None:
        first = seeder.seed_all()
        second = seeder.seed_all()
        assert first["document_sections"] == second["document_sections"]

    def test_failed_seed_rolls_back_everything(
        self, session: Session, tmp_path: Any
    ) -> None:
        data = tmp_path / "data"
        (data / "knowledge_base").mkdir(parents=True)
        (data / "customers.json").write_text(
            json.dumps(self.source("customers.json")), encoding="utf-8"
        )
        # orders.json has a row without the required order_id.
        (data / "orders.json").write_text(json.dumps([{"customer_id": "cus_1001"}]), encoding="utf-8")
        seeder = SeedHelper(
            session,
            DataFileReader(tmp_path, data),
            KnowledgeDocumentParser(),
            DocumentHelper(session),
        )
        with pytest.raises(ValidationError) as info:
            seeder.seed_all()
        assert info.value.details == {"missing_field": "order_id"}
        assert session.execute(select(Customer)).scalars().all() == []


class TestDocumentHelper(SeedTestCase):
    def test_upsert_reports_outcomes(self, session: Session) -> None:
        parser = KnowledgeDocumentParser()
        helper = DocumentHelper(session)
        v1 = parser.parse("# T\n\nDoc ID: KB-X-1\nAudience: A\nVersion: 1\n\n## S\n\nold text", "x.md")
        v2 = parser.parse("# T\n\nDoc ID: KB-X-1\nAudience: A\nVersion: 2\n\n## S\n\nnew text", "x.md")
        assert helper.upsert(v1) == DocumentHelper.CREATED
        assert helper.upsert(v1) == DocumentHelper.UNCHANGED
        assert helper.upsert(v2) == DocumentHelper.UPDATED
        assert helper.count() == 1
        assert helper.section_count() == 1
        fts = TableNames.documents_fts()
        body = session.execute(text(f"SELECT body FROM {fts} WHERE doc_id='KB-X-1'")).scalar_one()
        assert body == "new text"
