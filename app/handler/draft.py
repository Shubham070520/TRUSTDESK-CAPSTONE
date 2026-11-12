from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.common.schema import DraftReplyData, RecommendedActionOut
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.draft import DraftHelper


class DraftHandler(BaseHandler):
    def __init__(self, helper: DraftHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def create_draft(self, ticket_id: str) -> JSONResponse:
        return self.execute(partial(self._create, ticket_id), SuccessConfig.DRAFT_GENERATED)

    def _create(self, ticket_id: str) -> dict[str, Any]:
        ticket_id = self.validate_identifier(ticket_id, "ticket_id")
        outcome = self._helper.create_draft(ticket_id)
        draft = outcome.draft
        data = DraftReplyData(
            draft_id=draft.uuid,
            ticket_id=draft.ticket_id,
            status=draft.status.value,
            body=draft.body,
            citations=draft.citations,
            recommended_actions=[
                RecommendedActionOut(
                    tool_name=item.tool_name,
                    requires_human_approval=item.requires_human_approval,
                    reason=item.reason,
                )
                for item in outcome.recommendations.recommended
            ],
            needs_escalation=outcome.needs_escalation,
            guardrail_flagged=outcome.guardrail.flagged,
            guardrail_reasons=[reason.value for reason in outcome.guardrail.reasons],
            run_id=outcome.run_id,
        )
        return data.model_dump(mode="json")
