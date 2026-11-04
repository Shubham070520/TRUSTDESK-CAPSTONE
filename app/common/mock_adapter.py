import re
from typing import ClassVar

from app.common.enums import Sentiment, TicketCategory, TicketPriority
from app.common.mock_draft_templates import MockDraftTemplates
from app.common.model_adapter import (
    DocumentContext,
    DraftResult,
    ModelAdapter,
    TicketContext,
    TriageResult,
)
from app.common.ticket_signals import TicketSignals


class RuleBasedMockAdapter(ModelAdapter):
    """Deterministic adapter for tests and evals. No network, no randomness, no clock.

    Triage reads only the ticket text and its order context. Rule order matters:
    a safety hazard outranks everything, and a damage report outranks shipping
    wording such as "tracking says delivered".

    Draft cites a policy only if it was among the documents given. Otherwise it
    says the answer cannot be confirmed, so a dropped document cannot be cited.
    """

    _SECRET_REQUEST: ClassVar[re.Pattern[str]] = re.compile(
        r"system prompt|api key|internal (notes|instructions)"
    )

    _SAFETY: ClassVar[re.Pattern[str]] = TicketSignals.SAFETY
    _ACCOUNT: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(change|update|reset)\b.{0,30}\b(e-?mail|password)\b|\bpassword\b|verification"
        r"|identity check|locked out|account (is )?(locked|hacked|compromised)"
        r"|system prompt|api key|internal (notes|instructions)"
    )
    _DUPLICATE_CHARGE: ClassVar[re.Pattern[str]] = TicketSignals.DUPLICATE_CHARGE
    _BILLING: ClassVar[re.Pattern[str]] = re.compile(r"overcharg|\binvoice\b|\bbilling\b")
    _WARRANTY: ClassVar[re.Pattern[str]] = re.compile(r"\bwarranty\b|\bbattery\b")
    _DEFECT: ClassVar[re.Pattern[str]] = TicketSignals.DEFECT
    _DAMAGE: ClassVar[re.Pattern[str]] = TicketSignals.DAMAGE
    _STALE_TRACKING: ClassVar[re.Pattern[str]] = TicketSignals.STALE_TRACKING
    _SHIPPING: ClassVar[re.Pattern[str]] = re.compile(
        r"\btracking\b|in transit|\bcourier\b|\bcarrier\b|\bshipment\b|not (been )?delivered"
    )
    _REFUND: ClassVar[re.Pattern[str]] = re.compile(r"\brefund|\breturn|money back|final[- ]sale")
    _URGENT_NEED: ClassVar[re.Pattern[str]] = re.compile(
        r"\burgent|\basap\b|\bdeadline\b|\btravel|next week|\btomorrow\b|\btoday\b"
    )
    _ANGRY: ClassVar[re.Pattern[str]] = re.compile(
        r"\bangry\b|furious|unacceptable|ridiculous|disgust|\bscam\b|\bworst\b"
    )
    _WORRIED: ClassVar[re.Pattern[str]] = re.compile(r"worried|\bscared\b|\bafraid\b|dangerous")
    _FRUSTRATED: ClassVar[re.Pattern[str]] = re.compile(
        r"frustrat|disappoint|annoy|fed up|fix this|quickly"
    )

    @property
    def name(self) -> str:
        return "mock"

    def triage(self, ticket: TicketContext) -> TriageResult:
        text = TicketSignals.text_of(ticket)
        hazard = bool(self._SAFETY.search(text))
        category = self._category(ticket, text, hazard)
        priority, why = self._priority(ticket, text, hazard, category)
        return TriageResult(
            category=category,
            priority=priority,
            sentiment=self._sentiment(text, hazard),
            should_escalate=hazard,
            reason_summary=f"Category {category.value}, priority {priority.value}: {why}.",
        )

    def draft(
        self,
        ticket: TicketContext,
        triage: TriageResult,
        documents: list[DocumentContext],
    ) -> DraftResult:
        text = TicketSignals.text_of(ticket)
        doc_id, template, escalate = self._choose_template(ticket, triage, text)
        if doc_id is None or doc_id not in {document.doc_id for document in documents}:
            return DraftResult(MockDraftTemplates.CANNOT_CONFIRM, [], True)
        item = ticket.order.items[0].name if ticket.order and ticket.order.items else None
        body = template.format(item=item or MockDraftTemplates.DEFAULT_ITEM)
        return DraftResult(
            MockDraftTemplates.GREETING.format(name=ticket.customer.name, body=body),
            [doc_id],
            escalate,
        )

    # ---- draft rules ------------------------------------------------------

    def _choose_template(
        self, ticket: TicketContext, triage: TriageResult, text: str
    ) -> tuple[str | None, str, bool]:
        """The policy to cite, the reply text, and whether a human must take over."""
        templates = MockDraftTemplates
        if self._SAFETY.search(text):
            return templates.WARRANTY_DOC, templates.SAFETY, True
        if self._SECRET_REQUEST.search(text):
            return templates.SECURITY_DOC, templates.SECRET_REFUSAL, True
        if triage.category is TicketCategory.ACCOUNT_SECURITY:
            needs_human = triage.should_escalate or not ticket.customer.verified
            return templates.ACCOUNT_DOC, templates.ACCOUNT, needs_human
        if triage.should_escalate:
            refusal = templates.INJECTION_REFUSAL
            if "coupon" in text:
                refusal += templates.COUPON_REFUSAL
            return templates.SECURITY_DOC, refusal, True
        if triage.category is TicketCategory.REFUND:
            return self._refund_template(ticket, text)
        if triage.category is TicketCategory.SHIPPING:
            return self._shipping_template(triage, text)
        if triage.category is TicketCategory.WARRANTY:
            return templates.WARRANTY_DOC, templates.WARRANTY, False
        if triage.category is TicketCategory.BILLING:
            return templates.BILLING_DOC, templates.BILLING, False
        return None, templates.CANNOT_CONFIRM, True

    def _refund_template(self, ticket: TicketContext, text: str) -> tuple[str, str, bool]:
        templates = MockDraftTemplates
        doc_id = templates.REFUND_DOC
        inside = self._inside_return_window(ticket)
        if self._DAMAGE.search(text) or self._DEFECT.search(text):
            if inside:
                return doc_id, templates.DAMAGE_IN_WINDOW, False
            return doc_id, templates.DAMAGE_LATE, True
        order = ticket.order
        if order is not None and order.items and all(item.final_sale for item in order.items):
            return doc_id, templates.FINAL_SALE, False
        if order is not None and order.eligible_return_until and not inside:
            return doc_id, templates.REFUND_LATE, False
        return doc_id, templates.REFUND_IN_WINDOW, False

    def _shipping_template(self, triage: TriageResult, text: str) -> tuple[str, str, bool]:
        templates = MockDraftTemplates
        if not self._STALE_TRACKING.search(text):
            return templates.SHIPPING_DOC, templates.SHIPPING_STATUS, False
        body = templates.STALE_TRACKING
        if triage.priority is TicketPriority.HIGH:
            body += templates.URGENT_NOTE
        return templates.SHIPPING_DOC, body, False

    # ---- triage rules -----------------------------------------------------

    def _category(self, ticket: TicketContext, text: str, hazard: bool) -> TicketCategory:
        if hazard:
            return TicketCategory.WARRANTY
        if self._ACCOUNT.search(text):
            return TicketCategory.ACCOUNT_SECURITY
        if self._DUPLICATE_CHARGE.search(text) or self._BILLING.search(text):
            return TicketCategory.BILLING
        if self._WARRANTY.search(text):
            return TicketCategory.WARRANTY
        if self._DEFECT.search(text):
            if self._inside_return_window(ticket):
                return TicketCategory.REFUND
            return TicketCategory.WARRANTY
        if self._DAMAGE.search(text):
            return TicketCategory.REFUND
        if self._SHIPPING.search(text) or self._STALE_TRACKING.search(text):
            return TicketCategory.SHIPPING
        if self._REFUND.search(text):
            return TicketCategory.REFUND
        return TicketCategory.GENERAL

    def _priority(
        self, ticket: TicketContext, text: str, hazard: bool, category: TicketCategory
    ) -> tuple[TicketPriority, str]:
        if hazard:
            return TicketPriority.URGENT, "the ticket reports a product safety hazard"
        if category is TicketCategory.ACCOUNT_SECURITY:
            return TicketPriority.HIGH, "the ticket touches account security or sensitive data"
        if category is TicketCategory.BILLING and self._DUPLICATE_CHARGE.search(text):
            return TicketPriority.HIGH, "the customer reports a duplicate charge"
        if (
            category is TicketCategory.SHIPPING
            and self._STALE_TRACKING.search(text)
            and self._URGENT_NEED.search(text)
        ):
            return TicketPriority.HIGH, "tracking is stale and the customer has an urgent need"
        if category is TicketCategory.REFUND:
            return self._refund_priority(ticket, text)
        return TicketPriority.MEDIUM, "no high-impact signal in the ticket"

    def _refund_priority(self, ticket: TicketContext, text: str) -> tuple[TicketPriority, str]:
        if self._DAMAGE.search(text) or self._DEFECT.search(text):
            where = "inside" if self._inside_return_window(ticket) else "outside"
            return TicketPriority.MEDIUM, f"damage or a defect reported {where} the return window"
        order = ticket.order
        if order is None:
            return TicketPriority.MEDIUM, "refund request with no linked order"
        if order.items and all(item.final_sale for item in order.items):
            return TicketPriority.LOW, "refund request for a final-sale item"
        if order.eligible_return_until and not self._inside_return_window(ticket):
            return TicketPriority.LOW, "refund request after the return window ended"
        return TicketPriority.MEDIUM, "refund request inside the return window"

    def _sentiment(self, text: str, hazard: bool) -> Sentiment:
        if self._ANGRY.search(text):
            return Sentiment.ANGRY
        if hazard or self._WORRIED.search(text):
            return Sentiment.WORRIED
        if (
            self._FRUSTRATED.search(text)
            or self._DAMAGE.search(text)
            or self._DEFECT.search(text)
            or self._STALE_TRACKING.search(text)
        ):
            return Sentiment.FRUSTRATED
        return Sentiment.NEUTRAL

    @staticmethod
    def _inside_return_window(ticket: TicketContext) -> bool:
        return TicketSignals.inside_return_window(ticket)
