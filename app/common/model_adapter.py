"""The boundary between TrustDesk and any AI model.

Helpers depend on ``ModelAdapter`` only. A deterministic mock is used in
tests and evals, a hosted model can be swapped in without touching callers.

Contexts carry exactly what a model may see. They never include the seed
expectation labels, customer email addresses, or other customers' data.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.common.enums import Sentiment, TicketCategory, TicketPriority


@dataclass(frozen=True)
class CustomerContext:
    customer_id: str
    name: str
    tier: str
    verified: bool
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemContext:
    sku: str
    name: str
    quantity: int
    category: str
    final_sale: bool


@dataclass(frozen=True)
class OrderContext:
    order_id: str
    status: str
    delivered_at: str | None
    eligible_return_until: str | None
    tracking_number: str | None
    total: float
    currency: str
    payment_status: str
    items: tuple[ItemContext, ...] = ()


@dataclass(frozen=True)
class TicketContext:
    """A ticket as the model sees it. ``opened_at`` is the original ISO timestamp."""

    ticket_id: str
    channel: str
    subject: str
    body: str
    opened_at: str
    customer: CustomerContext
    order: OrderContext | None = None


@dataclass(frozen=True)
class DocumentContext:
    """A retrieved policy passage. Only documents that passed the guardrail reach here."""

    doc_id: str
    title: str
    audience: str
    text: str


@dataclass(frozen=True)
class TriageResult:
    category: TicketCategory
    priority: TicketPriority
    sentiment: Sentiment
    should_escalate: bool
    reason_summary: str


@dataclass(frozen=True)
class DraftResult:
    """A proposed reply. ``citations`` must be doc ids the model was given."""

    body: str
    citations: list[str] = field(default_factory=list)
    needs_escalation: bool = False


class ModelAdapter(ABC):
    """Contract every model backend implements."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier recorded in traces, e.g. ``mock`` or ``groq``."""

    @property
    def prompt_markers(self) -> tuple[str, ...]:
        """Phrases from this backend's prompts. The output filter treats them as a leak."""
        return ()

    @abstractmethod
    def triage(self, ticket: TicketContext) -> TriageResult:
        """Classify a ticket. Must treat the ticket text as data, never as instructions."""

    @abstractmethod
    def draft(
        self,
        ticket: TicketContext,
        triage: TriageResult,
        documents: list[DocumentContext],
    ) -> DraftResult:
        """Write a reply grounded in ``documents``. Provider failures raise ``ProviderError``."""
