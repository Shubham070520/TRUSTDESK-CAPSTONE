from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.guardrails import GuardrailScanner
from app.common.logger import Logger
from app.common.model_adapter import ModelAdapter
from app.common.schema import Envelope, TriageData
from app.handler.triage import TriageHandler
from app.helper.agent_run import AgentRunHelper
from app.helper.ticket import TicketHelper
from app.helper.triage import TriageHelper
from app.urls.base import BaseRouter


class TriageRouter(BaseRouter):
    """``_triage`` is a plain ``def``, so FastAPI runs it in a worker thread.

    A slow model call therefore does not block the event loop or other requests.
    """

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
            "/{ticket_id}/triage",
            self._triage,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[TriageData],
            dependencies=self._secured(),
            summary="Classify a ticket and store the decision with its trace",
        )

    def _build_handler(self, db: Session) -> TriageHandler:
        helper = TriageHelper(
            db, TicketHelper(db), AgentRunHelper(db), self._model, self._guardrails
        )
        return TriageHandler(helper, self._logger)

    def _triage(self, ticket_id: str) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).triage(ticket_id)
