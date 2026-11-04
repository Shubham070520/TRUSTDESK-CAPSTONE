from http import HTTPStatus
from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.common.auth import AuthDependency, Principal
from app.common.database import Database
from app.common.guardrails import GuardrailScanner
from app.common.logger import Logger
from app.common.schema import (
    Envelope,
    ToolActionApproveRequest,
    ToolActionCreateRequest,
    ToolActionData,
)
from app.handler.tool_action import ToolActionHandler
from app.helper.agent_run import AgentRunHelper
from app.helper.ticket import TicketHelper
from app.helper.tool_action import ToolActionHelper
from app.urls.base import BaseRouter


class ToolActionRouter(BaseRouter):
    """Every route needs the caller's identity for the audit, so ``auth`` is required.

    The inner functions exist because ``Depends`` needs this instance's ``auth`` when
    the route is declared. The actor always comes from the token, never the request body.
    """

    def __init__(
        self,
        database: Database,
        logger: Logger,
        guardrails: GuardrailScanner,
        auth: AuthDependency,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        super().__init__(database, logger, prefix=prefix, tags=tags, auth=auth)
        self._guardrails = guardrails

    def register_routes(self) -> None:
        current_user = Depends(self._auth)

        def request_action(
            body: ToolActionCreateRequest, principal: Principal = current_user
        ) -> Any:
            return self._request(body, principal)

        def approve(
            action_id: str, body: ToolActionApproveRequest, principal: Principal = current_user
        ) -> Any:
            return self._approve(action_id, body, principal)

        def execute(action_id: str, principal: Principal = current_user) -> Any:
            return self._execute(action_id, principal)

        self._router.add_api_route(
            "",
            request_action,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[ToolActionData],
            summary="Request a tool action. A retry with the same key returns the same action",
        )
        self._router.add_api_route(
            "/{action_id}/approve",
            approve,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[ToolActionData],
            summary="Record a human decision: approved or rejected",
        )
        self._router.add_api_route(
            "/{action_id}/execute",
            execute,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[ToolActionData],
            summary="Execute an approved action. A repeat returns the stored result",
        )

    def _build_handler(self, db: Session) -> ToolActionHandler:
        helper = ToolActionHelper(db, TicketHelper(db), AgentRunHelper(db), self._guardrails)
        return ToolActionHandler(helper, self._logger)

    def _request(self, body: ToolActionCreateRequest, principal: Principal) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).request_action(body, principal)

    def _approve(
        self, action_id: str, body: ToolActionApproveRequest, principal: Principal
    ) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).decide(action_id, body, principal)

    def _execute(self, action_id: str, principal: Principal) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).execute_action(action_id, principal)
