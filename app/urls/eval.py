from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.guardrails import GuardrailScanner
from app.common.logger import Logger
from app.common.model_adapter import ModelAdapter
from app.common.schema import Envelope, EvalRunData, EvalRunRequest
from app.handler.eval import EvalHandler
from app.helper.eval import EvalHelper
from app.urls.base import BaseRouter


class EvalRouter(BaseRouter):
    """``_run`` is a plain ``def``, so a long evaluation stays in a worker thread."""

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
            "",
            self._run,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[EvalRunData],
            dependencies=self._secured(),
            summary="Run all or selected eval cases and store the result",
        )
        self._router.add_api_route(
            "/{eval_run_id}",
            self._get,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[EvalRunData],
            dependencies=self._secured(),
            summary="A stored evaluation run",
        )

    def _build_handler(self, db: Session) -> EvalHandler:
        return EvalHandler(EvalHelper.compose(db, self._model, self._guardrails), self._logger)

    def _run(self, body: EvalRunRequest | None = None) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).run(body)

    def _get(self, eval_run_id: str) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).get_run(eval_run_id)
