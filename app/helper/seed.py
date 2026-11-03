from datetime import date
from typing import Any, ClassVar, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.data_reader import DataFileReader
from app.common.document_parser import KnowledgeDocumentParser
from app.common.exceptions import AppException, ValidationError
from app.helper.base import BaseHelper
from app.helper.document import DocumentHelper
from app.models.base import BaseModel
from app.models.customer import Customer
from app.models.eval_case import EvalCase
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.ticket_label import TicketLabel
from app.models.tool import Tool

M = TypeVar("M", bound=BaseModel)


class SeedHelper(BaseHelper):
    """Loads the provided data files into the database.

    * Idempotent: rows are upserted by their business key.
    * Atomic: everything is committed once, or rolled back.
    * Expected labels go only to ``TicketLabel`` and ``EvalCase``.
    * Re-seeding never overwrites triage results stored on a ticket.
    """

    CUSTOMERS_FILE: ClassVar[str] = "customers.json"
    ORDERS_FILE: ClassVar[str] = "orders.json"
    TICKETS_FILE: ClassVar[str] = "tickets.json"
    TOOLS_FILE: ClassVar[str] = "tool_actions.json"
    EVAL_FILE: ClassVar[str] = "eval_cases.jsonl"

    def __init__(
        self,
        db: Session,
        reader: DataFileReader,
        parser: KnowledgeDocumentParser,
        documents: DocumentHelper,
    ) -> None:
        super().__init__(db)
        self._reader = reader
        self._parser = parser
        self._documents = documents

    def seed_all(self) -> dict[str, int]:
        """Seed everything and return the row count of each seeded table."""
        try:
            with self._guard():
                self._seed_customers(self._reader.read_json(self.CUSTOMERS_FILE))
                self._seed_orders(self._reader.read_json(self.ORDERS_FILE))
                tickets = self._reader.read_json(self.TICKETS_FILE)
                self._seed_tickets(tickets)
                self._seed_ticket_labels(tickets)
                self._seed_tools(self._reader.read_json(self.TOOLS_FILE))
                self._seed_eval_cases(self._reader.read_jsonl(self.EVAL_FILE))
                self._seed_documents()
                self.db.commit()
        except KeyError as exc:
            self.rollback()
            raise ValidationError(details={"missing_field": str(exc.args[0])}) from exc
        except AppException:
            self.rollback()
            raise
        return self.counts()

    def counts(self) -> dict[str, int]:
        """Row count per seeded table, plus search-index sections."""
        with self._guard():
            result = {
                "customers": self._count(Customer),
                "orders": self._count(Order),
                "tickets": self._count(Ticket),
                "ticket_labels": self._count(TicketLabel),
                "tools": self._count(Tool),
                "eval_cases": self._count(EvalCase),
                "documents": self._documents.count(),
                "document_sections": self._documents.section_count(),
            }
        return result

    # ---- per-file loaders -------------------------------------------------

    def _seed_customers(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                Customer,
                "customer_id",
                row["customer_id"],
                {
                    "name": row["name"],
                    "email": row["email"],
                    "tier": row["tier"],
                    "country": row["country"],
                    "customer_since": row["created_at"],
                    "verified": row["verified"],
                    "tags": row.get("tags", []),
                },
            )
        self.db.flush()

    def _seed_orders(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                Order,
                "order_id",
                row["order_id"],
                {
                    "customer_id": row["customer_id"],
                    "status": row["status"],
                    "placed_at": self._to_date(row.get("placed_at")),
                    "delivered_at": self._to_date(row.get("delivered_at")),
                    "eligible_return_until": self._to_date(row.get("eligible_return_until")),
                    "total": row["total"],
                    "currency": row["currency"],
                    "payment_status": row["payment_status"],
                    "tracking_number": row.get("tracking_number"),
                    "items": row.get("items", []),
                },
            )
        self.db.flush()

    def _seed_tickets(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                Ticket,
                "ticket_id",
                row["ticket_id"],
                {
                    "customer_id": row["customer_id"],
                    "order_id": row.get("order_id"),
                    "channel": row["channel"],
                    "subject": row["subject"],
                    "body": row["body"],
                    "opened_at": row["created_at"],
                    "status": row["status"],
                },
            )
        self.db.flush()

    def _seed_ticket_labels(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                TicketLabel,
                "ticket_id",
                row["ticket_id"],
                {
                    "expected_category": row["expected_category"],
                    "expected_priority": row["expected_priority"],
                    "expected_sentiment": row["expected_sentiment"],
                    "expected_escalation": row["expected_escalation"],
                    "expected_actions": row.get("expected_actions", []),
                },
            )
        self.db.flush()

    def _seed_tools(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                Tool,
                "tool_name",
                row["tool_name"],
                {
                    "description": row["description"],
                    "risk_level": row["risk_level"],
                    "requires_human_approval": row["requires_human_approval"],
                    "allowed_categories": row.get("allowed_categories", []),
                    "required_fields": row.get("required_fields", []),
                    "max_amount_inr": row.get("max_amount_inr"),
                },
            )
        self.db.flush()

    def _seed_eval_cases(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._upsert(
                EvalCase,
                "case_id",
                row["case_id"],
                {
                    "ticket_id": row["ticket_id"],
                    "input": row["input"],
                    "expected": row["expected"],
                },
            )
        self.db.flush()

    def _seed_documents(self) -> None:
        seen: set[str] = set()
        for source in self._reader.read_knowledge_files():
            parsed = self._parser.parse(source.text, source.relative_path)
            if parsed.doc_id in seen:
                raise ValidationError(details={"duplicate_doc_id": parsed.doc_id})
            seen.add(parsed.doc_id)
            self._documents.upsert(parsed)

    # ---- shared pieces ----------------------------------------------------

    def _upsert(self, model: type[M], key_field: str, key: str, values: dict[str, Any]) -> M:
        """Create the row for ``key`` or update it in place. Revives soft-deleted rows."""
        column = getattr(model, key_field)
        instance = self.db.execute(select(model).where(column == key)).scalar_one_or_none()
        if instance is None:
            instance = model(**{key_field: key})
            self.db.add(instance)
        for name, value in values.items():
            setattr(instance, name, value)
        instance.is_deleted = False
        return instance

    def _count(self, model: type[BaseModel]) -> int:
        return int(self.db.execute(select(func.count(model.id))).scalar_one())

    @staticmethod
    def _to_date(value: str | None) -> date | None:
        return date.fromisoformat(value) if value else None
