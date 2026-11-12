from dataclasses import dataclass
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.common.exceptions import ProviderError
from app.common.guardrails import GuardrailResult, GuardrailScanner, ScannableDocument
from app.common.model_adapter import DocumentContext, DraftResult, ModelAdapter, TriageResult
from app.config import Config
from app.helper.action import ActionHelper, RecommendationSet
from app.helper.agent_run import AgentRunHelper
from app.helper.base import BaseHelper
from app.helper.document import DocumentHelper
from app.helper.ticket import TicketHelper
from app.helper.triage import TriageHelper
from app.models.agent_run import AgentRun
from app.models.draft import Draft
from app.models.enums import DraftStatus, RunStatus, RunType


@dataclass(frozen=True)
class DraftOutcome:
    draft: Draft
    needs_escalation: bool
    run_id: str
    guardrail: GuardrailResult
    recommendations: RecommendationSet


@dataclass(frozen=True)
class RetrievedDocuments:
    """Search results split by the guardrail. Only ``safe`` may reach the model."""

    retrieved_ids: list[str]
    safe: list[DocumentContext]
    dropped: list[dict[str, Any]]


class DraftHelper(BaseHelper):
    """Writes one reply: retrieve, drop unsafe documents, call the model, validate, store.

    A proposed reply is kept only if it cites at least one document the model was
    given, cites nothing else, and passes the output filter. Otherwise the customer
    gets a fixed escalation reply and the model's text is discarded. Tool actions are
    decided afterwards by ``ActionHelper``, not by the model. No connection is held
    during the model call. The draft and its trace are committed together.

    Traces hold document and output reasons but not their evidence, so a blocked
    secret or a vendor note's instruction text cannot come back through the trace API.
    """

    ESCALATION_BODY: ClassVar[str] = (
        "I cannot confirm an answer to this from our support policies, "
        "so I have passed your request to a human support specialist."
    )

    NO_DOCUMENTS: ClassVar[str] = "no_documents"
    NO_CITATIONS: ClassVar[str] = "no_citations"
    FABRICATED_CITATION: ClassVar[str] = "fabricated_citation"
    OUTPUT_BLOCKED: ClassVar[str] = "output_blocked"

    _MAX_TRACED_CITATIONS: ClassVar[int] = 10
    _MAX_TRACED_CITATION_CHARS: ClassVar[int] = 64

    def __init__(
        self,
        db: Session,
        tickets: TicketHelper,
        triage: TriageHelper,
        documents: DocumentHelper,
        actions: ActionHelper,
        runs: AgentRunHelper,
        model: ModelAdapter,
        guardrails: GuardrailScanner,
    ) -> None:
        super().__init__(db)
        self._tickets = tickets
        self._triage = triage
        self._documents = documents
        self._actions = actions
        self._runs = runs
        self._model = model
        self._guardrails = guardrails

    def create_draft(
        self,
        ticket_id: str,
        triage: TriageResult | None = None,
        run_type: RunType = RunType.DRAFT_REPLY,
        store_draft: bool = True,
    ) -> DraftOutcome:
        """The defaults are the API's. The evaluator passes a fresh triage and stores no draft."""
        detail = self._tickets.get_ticket_detail(ticket_id)
        triage = triage if triage is not None else self._triage.current(detail.ticket)
        context = self._tickets.build_context(detail)
        customer_email = detail.customer.email
        scan = self._guardrails.scan_input(f"{context.subject}\n{context.body}")
        retrieved = self._retrieve(f"{triage.category.value} {context.subject} {context.body}")
        self.rollback()  # ends the read and returns the connection before the slow call

        trace: dict[str, Any] = {
            "input": scan.to_dict(),
            "documents": {"dropped": retrieved.dropped},
        }
        proposed: DraftResult | None = None
        if retrieved.safe:
            try:
                proposed = self._model.draft(context, triage, retrieved.safe)
            except ProviderError as exc:
                run = self._record_run(ticket_id, run_type, RunStatus.FAILED, retrieved, trace)
                self.commit()
                raise ProviderError(details={**(exc.details or {}), "run_id": run.uuid}) from exc

        body, citations, escalate = self._validate(proposed, retrieved, customer_email, trace)
        recommendations = self._actions.recommend(
            context, triage, scan, needs_escalation=escalate
        )
        draft = Draft(
            ticket_id=ticket_id, status=DraftStatus.GENERATED, body=body, citations=citations
        )
        if store_draft:
            with self._guard():
                self.db.add(draft)
        run = self._record_run(
            ticket_id, run_type, RunStatus.COMPLETED, retrieved, trace, recommendations.to_trace()
        )
        self.commit()
        return DraftOutcome(draft, recommendations.escalated, run.uuid, scan, recommendations)

    def _retrieve(self, query: str) -> RetrievedDocuments:
        """Search, then judge each hit on its whole text, not on the matching snippet."""
        hits = self._documents.search(query, Config.DRAFT_RETRIEVAL_K)
        documents = self._documents.get_many([hit.doc_id for hit in hits])
        safe: list[DocumentContext] = []
        dropped: list[dict[str, Any]] = []
        for hit in hits:
            document = documents.get(hit.doc_id)
            if document is None:
                continue
            result = self._guardrails.scan_document(
                ScannableDocument(document.doc_id, document.audience, document.content)
            )
            if result.flagged:
                reasons = [reason.value for reason in result.reasons]
                dropped.append({"doc_id": document.doc_id, "reasons": reasons})
            else:
                safe.append(
                    DocumentContext(
                        document.doc_id, document.title, document.audience, document.content
                    )
                )
        return RetrievedDocuments([hit.doc_id for hit in hits], safe, dropped)

    def _validate(
        self,
        proposed: DraftResult | None,
        retrieved: RetrievedDocuments,
        customer_email: str,
        trace: dict[str, Any],
    ) -> tuple[str, list[str], bool]:
        """Return the body, citations and escalation to store, and fill in the trace."""
        if proposed is None:
            trace["output"] = {"flagged": False, "reasons": []}
            trace["draft"] = {"rejected": self.NO_DOCUMENTS, "invalid_citations": []}
            return self.ESCALATION_BODY, [], True

        allowed = {document.doc_id for document in retrieved.safe}
        citations = list(dict.fromkeys(proposed.citations))
        invalid = [citation for citation in citations if citation not in allowed]
        output = self._guardrails.filter_output(proposed.body, allowed_emails=[customer_email])
        rejected = self._rejection(citations, invalid, output)

        trace["output"] = {
            "flagged": output.flagged,
            "reasons": [reason.value for reason in output.reasons],
        }
        trace["draft"] = {
            "rejected": rejected,
            "invalid_citations": [
                citation[: self._MAX_TRACED_CITATION_CHARS]
                for citation in invalid[: self._MAX_TRACED_CITATIONS]
            ],
        }
        if rejected is not None:
            return self.ESCALATION_BODY, [], True
        return proposed.body, citations, proposed.needs_escalation

    def _rejection(
        self, citations: list[str], invalid: list[str], output: GuardrailResult
    ) -> str | None:
        if invalid:
            return self.FABRICATED_CITATION
        if not citations:
            return self.NO_CITATIONS
        if output.flagged:
            return self.OUTPUT_BLOCKED
        return None

    def _record_run(
        self,
        ticket_id: str,
        run_type: RunType,
        status: RunStatus,
        retrieved: RetrievedDocuments,
        trace: dict[str, Any],
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> AgentRun:
        return self._runs.create(
            ticket_id=ticket_id,
            run_type=run_type,
            status=status,
            guardrail_results=trace,
            retrieved_doc_ids=retrieved.retrieved_ids,
            tool_calls=tool_calls,
        )
