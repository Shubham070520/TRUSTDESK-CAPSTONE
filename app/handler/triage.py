from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.common.schema import TriageData
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.triage import TriageHelper


class TriageHandler(BaseHandler):
    def __init__(self, helper: TriageHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def triage(self, ticket_id: str) -> JSONResponse:
        return self.execute(partial(self._triage, ticket_id), SuccessConfig.TICKET_TRIAGED)

    def _triage(self, ticket_id: str) -> dict[str, Any]:
        ticket_id = self.validate_identifier(ticket_id, "ticket_id")
        outcome = self._helper.triage(ticket_id)
        result = outcome.result
        data = TriageData(
            ticket_id=outcome.ticket_id,
            category=result.category.value,
            priority=result.priority.value,
            sentiment=result.sentiment.value,
            should_escalate=result.should_escalate,
            reason_summary=result.reason_summary,
            run_id=outcome.run_id,
            guardrail_flagged=outcome.guardrail.flagged,
            guardrail_reasons=[reason.value for reason in outcome.guardrail.reasons],
        )
        return data.model_dump(mode="json")
