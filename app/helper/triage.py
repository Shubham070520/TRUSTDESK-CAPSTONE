from dataclasses import dataclass, replace
from typing import ClassVar

from sqlalchemy.orm import Session

from app.common.enums import Sentiment, TicketCategory, TicketPriority
from app.common.exceptions import ProviderError
from app.common.guardrails import GuardrailResult, GuardrailScanner
from app.common.model_adapter import ModelAdapter, TriageResult
from app.helper.agent_run import AgentRunHelper
from app.helper.base import BaseHelper
from app.helper.ticket import TicketHelper
from app.models.agent_run import AgentRun
from app.models.enums import RunStatus, RunType
from app.models.ticket import Ticket


@dataclass(frozen=True)
class TriageOutcome:
    ticket_id: str
    result: TriageResult
    run_id: str
    guardrail: GuardrailResult


class TriageHelper(BaseHelper):
    """Runs one triage: guardrail scan, model call, then stored result and trace.

    The scan runs before the model and a flag always forces escalation, whatever
    the model says. No connection is held during the model call, so a slow
    provider cannot starve other requests. The result and its trace are committed
    together. A provider failure leaves the ticket as it was and records a failed run.

    The model's reason is shown to reviewers, so it passes the output filter too. If it
    is blocked, a fixed text replaces it and the ticket escalates.
    """

    _FLAGGED_NOTE: ClassVar[str] = "Escalated because the guardrail flagged: {reasons}."
    _REASON_WITHHELD: ClassVar[str] = "The model's explanation was withheld by the output filter."

    def __init__(
        self,
        db: Session,
        tickets: TicketHelper,
        runs: AgentRunHelper,
        model: ModelAdapter,
        guardrails: GuardrailScanner,
    ) -> None:
        super().__init__(db)
        self._tickets = tickets
        self._runs = runs
        self._model = model
        self._guardrails = guardrails

    def triage(
        self,
        ticket_id: str,
        run_type: RunType = RunType.TRIAGE,
        store_on_ticket: bool = True,
    ) -> TriageOutcome:
        """``store_on_ticket=False`` writes only the trace; the evaluator uses it."""
        detail = self._tickets.get_ticket_detail(ticket_id)
        context = self._tickets.build_context(detail)
        scan = self._guardrails.scan_input(f"{context.subject}\n{context.body}")
        self.rollback()  # ends the read and returns the connection before the slow call

        try:
            proposed = self._model.triage(context)
        except ProviderError as exc:
            run = self._record_run(ticket_id, run_type, RunStatus.FAILED, scan)
            self.commit()
            raise ProviderError(details={**(exc.details or {}), "run_id": run.uuid}) from exc

        output = self._guardrails.filter_output(proposed.reason_summary)
        if output.flagged:
            proposed = replace(
                proposed, should_escalate=True, reason_summary=self._REASON_WITHHELD
            )
        result = self._apply_guardrail(proposed, scan)
        run = self._record_run(ticket_id, run_type, RunStatus.COMPLETED, scan, output)
        if store_on_ticket:
            self._store(detail.ticket, result, run.uuid)
        self.commit()
        return TriageOutcome(ticket_id, result, run.uuid, scan)

    def current(self, ticket: Ticket) -> TriageResult:
        """The ticket's stored triage, running one first if it has none."""
        if (
            ticket.triage_category is None
            or ticket.triage_priority is None
            or ticket.triage_sentiment is None
            or ticket.triage_escalate is None
        ):
            return self.triage(ticket.ticket_id).result
        return TriageResult(
            category=TicketCategory(ticket.triage_category),
            priority=TicketPriority(ticket.triage_priority),
            sentiment=Sentiment(ticket.triage_sentiment),
            should_escalate=ticket.triage_escalate,
            reason_summary=ticket.triage_reason or "",
        )

    def _apply_guardrail(self, result: TriageResult, scan: GuardrailResult) -> TriageResult:
        if scan.safe:
            return result
        reasons = ", ".join(reason.value for reason in scan.reasons)
        note = self._FLAGGED_NOTE.format(reasons=reasons)
        return replace(
            result, should_escalate=True, reason_summary=f"{result.reason_summary} {note}"
        )

    def _record_run(
        self,
        ticket_id: str,
        run_type: RunType,
        status: RunStatus,
        scan: GuardrailResult,
        output: GuardrailResult | None = None,
    ) -> AgentRun:
        trace = {"input": scan.to_dict()}
        if output is not None and output.flagged:
            # Reasons only: the evidence could be the very text that was blocked.
            trace["output"] = {
                "flagged": True,
                "reasons": [reason.value for reason in output.reasons],
            }
        return self._runs.create(
            ticket_id=ticket_id,
            run_type=run_type,
            status=status,
            guardrail_results=trace,
        )

    @staticmethod
    def _store(ticket: Ticket, result: TriageResult, run_id: str) -> None:
        ticket.triage_category = result.category.value
        ticket.triage_priority = result.priority.value
        ticket.triage_sentiment = result.sentiment.value
        ticket.triage_escalate = result.should_escalate
        ticket.triage_reason = result.reason_summary
        ticket.triage_run_id = run_id
