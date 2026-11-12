from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.eval_scoring import AnswerRequirements, CaseObservation, EvalScorer
from app.common.exceptions import AppException, ConflictError, ValidationError
from app.common.guardrails import GuardrailScanner
from app.common.model_adapter import ModelAdapter
from app.helper.action import ActionHelper
from app.helper.agent_run import AgentRunHelper
from app.helper.base import BaseHelper
from app.helper.document import DocumentHelper
from app.helper.draft import DraftHelper
from app.helper.ticket import TicketHelper
from app.helper.triage import TriageHelper
from app.models.enums import ActionStatus, RunType
from app.models.eval_case import EvalCase
from app.models.eval_run import EvalRun
from app.models.tool_action import ToolActionRequest


@dataclass(frozen=True)
class LoadedCase:
    case_id: str
    ticket_id: str
    summary: str
    expected: dict[str, Any]


class EvalHelper(BaseHelper):
    """Runs eval cases through the same triage and draft code as the API.

    This is the only code that reads ``EvalCase.expected``; it reaches ``EvalScorer``
    only after the system has answered. Each case gets a fresh triage. A run writes
    ``eval_case`` traces and an ``EvalRun`` row, and leaves each ticket's triage and
    drafts as they were, so an eval does not change what reviewers see. One failing
    case is scored as failed and the run carries on.
    """

    def __init__(
        self,
        db: Session,
        triage: TriageHelper,
        drafts: DraftHelper,
        runs: AgentRunHelper,
        scorer: EvalScorer,
        model_name: str,
    ) -> None:
        super().__init__(db)
        self._triage = triage
        self._drafts = drafts
        self._runs = runs
        self._scorer = scorer
        self._model_name = model_name

    @classmethod
    def compose(cls, db: Session, model: ModelAdapter, guardrails: GuardrailScanner) -> "EvalHelper":
        """Assembles the collaborators, for the router and the command-line entry point."""
        tickets = TicketHelper(db)
        runs = AgentRunHelper(db)
        triage = TriageHelper(db, tickets, runs, model, guardrails)
        drafts = DraftHelper(
            db, tickets, triage, DocumentHelper(db), ActionHelper(db), runs, model, guardrails
        )
        return cls(db, triage, drafts, runs, EvalScorer(AnswerRequirements()), model.name)

    def run(self, case_ids: list[str] | None = None) -> EvalRun:
        cases = self._load_cases(case_ids)
        started_at = self._now()
        results = [self._run_case(case) for case in cases]
        run = EvalRun(
            started_at=started_at,
            completed_at=self._now(),
            total_cases=len(results),
            metrics=self._scorer.summarize(results, self._model_name),
            case_results=results,
        )
        with self._guard():
            self.db.add(run)
            self.db.flush()
        self.commit()
        return run

    def get(self, eval_run_id: str) -> EvalRun:
        return self.get_by_uuid(EvalRun, eval_run_id)

    def _load_cases(self, case_ids: list[str] | None) -> list[LoadedCase]:
        with self._guard():
            rows = list(
                self.db.execute(
                    select(EvalCase).where(EvalCase.is_deleted.is_(False)).order_by(EvalCase.id)
                ).scalars()
            )
        if not rows:
            raise ConflictError(details={"reason": "no_eval_cases"})
        if case_ids is not None:
            known = {row.case_id for row in rows}
            unknown = sorted(set(case_ids) - known)
            if unknown:
                raise ValidationError(details={"reason": "unknown_cases", "case_ids": unknown})
            rows = [row for row in rows if row.case_id in set(case_ids)]
        return [LoadedCase(r.case_id, r.ticket_id, r.input, dict(r.expected)) for r in rows]

    def _run_case(self, case: LoadedCase) -> dict[str, Any]:
        seen = self._observe(case.ticket_id)
        return self._scorer.score(case.case_id, case.ticket_id, case.summary, case.expected, seen)

    def _observe(self, ticket_id: str) -> CaseObservation:
        executed = self._executed_tools(ticket_id)
        try:
            triage = self._triage.triage(
                ticket_id, run_type=RunType.EVAL_CASE, store_on_ticket=False
            )
            draft = self._drafts.create_draft(
                ticket_id, triage=triage.result, run_type=RunType.EVAL_CASE, store_draft=False
            )
        except AppException as exc:
            self.rollback()
            return CaseObservation(executed=executed, error=exc.message)
        trace = self._runs.get(draft.run_id)
        documents = trace.guardrail_results.get("documents", {})
        return CaseObservation(
            category=triage.result.category.value,
            priority=triage.result.priority.value,
            citations=list(draft.draft.citations),
            recommended=[item.tool_name for item in draft.recommendations.recommended],
            blocked=[item.tool_name for item in draft.recommendations.blocked],
            executed=executed,
            should_escalate=draft.needs_escalation,
            body=draft.draft.body,
            guardrail_reasons=[reason.value for reason in draft.guardrail.reasons],
            retrieved_doc_ids=list(trace.retrieved_doc_ids),
            dropped_doc_ids=[entry["doc_id"] for entry in documents.get("dropped", [])],
            run_ids=[triage.run_id, draft.run_id],
        )

    def _executed_tools(self, ticket_id: str) -> list[str]:
        """Tools really executed on this ticket, so a disallowed execution fails the case."""
        with self._guard():
            return list(
                self.db.execute(
                    select(ToolActionRequest.tool_name).where(
                        ToolActionRequest.ticket_id == ticket_id,
                        ToolActionRequest.status == ActionStatus.EXECUTED,
                    )
                ).scalars()
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
