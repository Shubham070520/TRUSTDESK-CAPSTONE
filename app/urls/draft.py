from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.guardrails import GuardrailScanner
from app.common.logger import Logger
from app.common.model_adapter import ModelAdapter
from app.common.schema import DraftReplyData, Envelope
from app.handler.draft import DraftHandler
from app.helper.action import ActionHelper
from app.helper.agent_run import AgentRunHelper
from app.helper.document import DocumentHelper
from app.helper.draft import DraftHelper
from app.helper.ticket import TicketHelper
from app.helper.triage import TriageHelper
from app.urls.base import BaseRouter


class DraftRouter(BaseRouter):
    """``_create`` is a plain ``def``, so FastAPI runs it in a worker thread."""

    def __init__(
        self,
        database: Database,
        logger: Logger,
        model: ModelAdapter,
        guardrails: GuardrailScanner,
        prefix: str = "",
        tags: list[str] | None = None,
        auth: AuthDependency | None = None,
    ) -> None:
        super().__init__(database, logger, prefix=prefix, tags=tags, auth=auth)
        self._model = model
        self._guardrails = guardrails

    def register_routes(self) -> None:
        self._router.add_api_route(
            "/{ticket_id}/draft-reply",
            self._create,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[DraftReplyData],
            dependencies=self._secured(),
            summary="Write a cited reply from retrieved policy and store it with its trace",
        )

    def _build_handler(self, db: Session) -> DraftHandler:
        tickets = TicketHelper(db)
        runs = AgentRunHelper(db)
        triage = TriageHelper(db, tickets, runs, self._model, self._guardrails)
        helper = DraftHelper(
            db,
            tickets,
            triage,
            DocumentHelper(db),
            ActionHelper(db),
            runs,
            self._model,
            self._guardrails,
        )
        return DraftHandler(helper, self._logger)

    def _create(self, ticket_id: str) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).create_draft(ticket_id)
