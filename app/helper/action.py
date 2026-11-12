from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from sqlalchemy import select

from app.common.guardrails import GuardrailResult
from app.common.model_adapter import ItemContext, TicketContext, TriageResult
from app.common.ticket_signals import TicketSignals
from app.helper.base import BaseHelper
from app.models.tool import Tool


class BlockReason(str, Enum):
    NEVER_RECOMMENDED = "never_recommended"
    NOT_IN_CATALOG = "not_in_catalog"
    CATEGORY_NOT_ALLOWED = "category_not_allowed"
    NO_ORDER = "no_order"
    FINAL_SALE = "final_sale"
    OUTSIDE_RETURN_WINDOW = "outside_return_window"
    GUARDRAIL_FLAGGED = "guardrail_flagged"
    TICKET_ESCALATED = "ticket_escalated"


@dataclass(frozen=True)
class Recommendation:
    tool_name: str
    requires_human_approval: bool
    reason: str


@dataclass(frozen=True)
class BlockedAction:
    tool_name: str
    reason: BlockReason


@dataclass(frozen=True)
class Proposal:
    """An action the ticket's facts point to, before the catalog and safety checks."""

    tool_name: str
    reason: str
    unmet_condition: BlockReason | None = None


@dataclass(frozen=True)
class RecommendationSet:
    recommended: list[Recommendation]
    blocked: list[BlockedAction]
    escalated: bool

    def to_trace(self) -> list[dict[str, Any]]:
        """JSON-friendly form for the ``tool_calls`` column of a trace."""
        recommended = [
            {
                "tool_name": item.tool_name,
                "status": "recommended",
                "requires_human_approval": item.requires_human_approval,
                "reason": item.reason,
            }
            for item in self.recommended
        ]
        blocked = [
            {"tool_name": item.tool_name, "status": "blocked", "reason": item.reason.value}
            for item in self.blocked
        ]
        return recommended + blocked


class ActionHelper(BaseHelper):
    """Decides which tool actions a reviewer should see for a ticket.

    Rules read the ticket, its order, the triage category, the guardrail scan and
    the tool catalog. No model chooses an action, and nothing is executed here.
    A proposal is blocked for the first failed check, in this order: never allowed,
    missing from the catalog, category not allowed, unmet policy condition, escalation.
    """

    REPLACEMENT: ClassVar[str] = "create_replacement_order"
    CARRIER_INVESTIGATION: ClassVar[str] = "open_carrier_investigation"
    REFUND_REVIEW: ClassVar[str] = "start_refund_review"
    ESCALATE: ClassVar[str] = "escalate_to_human"
    COUPON: ClassVar[str] = "issue_coupon"
    LOCK_ACCOUNT: ClassVar[str] = "lock_account"

    _NEVER_RECOMMENDED: ClassVar[frozenset[str]] = frozenset({COUPON, LOCK_ACCOUNT})

    def recommend(
        self,
        ticket: TicketContext,
        triage: TriageResult,
        guardrail: GuardrailResult,
        needs_escalation: bool = False,
    ) -> RecommendationSet:
        text = TicketSignals.text_of(ticket)
        hazard = bool(TicketSignals.SAFETY.search(text))
        escalated = needs_escalation or triage.should_escalate or guardrail.flagged or hazard
        catalog = self._catalog()

        recommended: list[Recommendation] = []
        blocked: list[BlockedAction] = []
        for proposal in self._propose(ticket, text, escalated):
            reason = self._block_reason(proposal, triage, guardrail, catalog, escalated)
            if reason is not None:
                blocked.append(BlockedAction(proposal.tool_name, reason))
                continue
            tool = catalog[proposal.tool_name]
            recommended.append(
                Recommendation(proposal.tool_name, tool.requires_human_approval, proposal.reason)
            )
        return RecommendationSet(recommended, blocked, escalated)

    def _propose(self, ticket: TicketContext, text: str, escalated: bool) -> list[Proposal]:
        proposals: list[Proposal] = []
        if escalated:
            proposals.append(
                Proposal(self.ESCALATE, "The ticket needs a human support specialist.")
            )
        if TicketSignals.DAMAGE.search(text) or TicketSignals.DEFECT.search(text):
            proposals.append(
                Proposal(
                    self.REPLACEMENT,
                    "Damaged or defective physical item reported within the return window.",
                    self._replacement_condition(ticket, text),
                )
            )
        if TicketSignals.STALE_TRACKING.search(text):
            proposals.append(
                Proposal(
                    self.CARRIER_INVESTIGATION,
                    "Tracking has stopped moving, so the carrier needs to investigate.",
                )
            )
        if TicketSignals.DUPLICATE_CHARGE.search(text):
            proposals.append(
                Proposal(
                    self.REFUND_REVIEW,
                    "The customer reports a duplicate charge, which needs a human-reviewed check.",
                )
            )
        if TicketSignals.COUPON.search(text):
            proposals.append(Proposal(self.COUPON, "The ticket mentions a coupon."))
        if TicketSignals.ACCOUNT_LOCK.search(text):
            proposals.append(Proposal(self.LOCK_ACCOUNT, "The ticket asks to lock an account."))
        return proposals

    def _replacement_condition(self, ticket: TicketContext, text: str) -> BlockReason | None:
        """The first unmet order condition for a replacement (Ref B, items 3 and 4)."""
        if ticket.order is None or not ticket.order.items:
            return BlockReason.NO_ORDER
        if any(item.final_sale for item in self._items_in_question(ticket.order.items, text)):
            return BlockReason.FINAL_SALE
        if not TicketSignals.inside_return_window(ticket):
            return BlockReason.OUTSIDE_RETURN_WINDOW
        return None

    @staticmethod
    def _items_in_question(items: tuple[ItemContext, ...], text: str) -> list[ItemContext]:
        """The items the ticket names. If it names none, every item counts, to stay cautious."""
        named = [item for item in items if item.name.casefold() in text]
        return named or list(items)

    def _block_reason(
        self,
        proposal: Proposal,
        triage: TriageResult,
        guardrail: GuardrailResult,
        catalog: dict[str, Tool],
        escalated: bool,
    ) -> BlockReason | None:
        if proposal.tool_name in self._NEVER_RECOMMENDED:
            return BlockReason.NEVER_RECOMMENDED
        tool = catalog.get(proposal.tool_name)
        if tool is None:
            return BlockReason.NOT_IN_CATALOG
        if triage.category.value not in tool.allowed_categories:
            return BlockReason.CATEGORY_NOT_ALLOWED
        if proposal.unmet_condition is not None:
            return proposal.unmet_condition
        if escalated and proposal.tool_name != self.ESCALATE:
            if guardrail.flagged:
                return BlockReason.GUARDRAIL_FLAGGED
            return BlockReason.TICKET_ESCALATED
        return None

    def _catalog(self) -> dict[str, Tool]:
        with self._guard():
            rows = self.db.execute(select(Tool).where(Tool.is_deleted.is_(False))).scalars()
            return {tool.tool_name: tool for tool in rows}
