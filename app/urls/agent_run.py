from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.schema import AgentRunOut, Envelope
from app.handler.agent_run import AgentRunHandler
from app.helper.agent_run import AgentRunHelper
from app.urls.base import BaseRouter


class AgentRunRouter(BaseRouter):
    def register_routes(self) -> None:
        self._router.add_api_route(
            "/{run_id}",
            self._get,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[AgentRunOut],
            dependencies=self._secured(),
            summary="Trace of one AI run",
        )

    def _build_handler(self, db: Session) -> AgentRunHandler:
        return AgentRunHandler(AgentRunHelper(db), self._logger)

    def _get(self, run_id: str) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).get_run(run_id)
