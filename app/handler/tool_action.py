from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.auth import Principal
from app.common.logger import Logger
from app.common.schema import (
    ApprovalOut,
    ToolActionApproveRequest,
    ToolActionCreateRequest,
    ToolActionData,
)
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.tool_action import ToolActionHelper, ToolActionOutcome
from app.models.enums import ApprovalDecision


class ToolActionHandler(BaseHandler):
    def __init__(self, helper: ToolActionHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def request_action(
        self, body: ToolActionCreateRequest, principal: Principal
    ) -> JSONResponse:
        return self.execute(
            partial(self._request, body, principal), SuccessConfig.TOOL_ACTION_REQUESTED
        )

    def decide(
        self, action_id: str, body: ToolActionApproveRequest, principal: Principal
    ) -> JSONResponse:
        return self.execute(
            partial(self._decide, action_id, body, principal), SuccessConfig.TOOL_ACTION_DECIDED
        )

    def execute_action(self, action_id: str, principal: Principal) -> JSONResponse:
        return self.execute(
            partial(self._execute, action_id, principal), SuccessConfig.TOOL_ACTION_EXECUTED
        )

    # ---- actions run inside ``execute`` -----------------------------------

    def _request(self, body: ToolActionCreateRequest, principal: Principal) -> dict[str, Any]:
        ticket_id = self.validate_identifier(body.ticket_id, "ticket_id")
        outcome = self._helper.request(
            ticket_id, body.tool_name, body.payload, principal.reviewer_id
        )
        return self._serialize(outcome)

    def _decide(
        self, action_id: str, body: ToolActionApproveRequest, principal: Principal
    ) -> dict[str, Any]:
        outcome = self._helper.decide(
            self.validate_uuid(action_id),
            ApprovalDecision(body.decision),
            body.reason,
            principal.reviewer_id,
        )
        return self._serialize(outcome)

    def _execute(self, action_id: str, principal: Principal) -> dict[str, Any]:
        outcome = self._helper.execute(self.validate_uuid(action_id), principal.reviewer_id)
        return self._serialize(outcome)

    @staticmethod
    def _serialize(outcome: ToolActionOutcome) -> dict[str, Any]:
        action = outcome.action
        approval = outcome.approval
        data = ToolActionData(
            action_id=action.uuid,
            ticket_id=action.ticket_id,
            tool_name=action.tool_name,
            payload=action.payload,
            risk_level=action.risk_level,
            requires_human_approval=action.requires_human_approval,
            status=action.status.value,
            idempotency_key=action.idempotency_key,
            result=action.result,
            created_at=action.created_at,
            approval=(
                ApprovalOut(
                    reviewer_id=approval.reviewer_id,
                    decision=approval.decision.value,
                    reason=approval.reason,
                    created_at=approval.created_at,
                )
                if approval is not None
                else None
            ),
            run_id=outcome.run_id,
            replayed=outcome.replayed,
        )
        return data.model_dump(mode="json")
