from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.exception_handlers import ExceptionHandlerRegistry
from app.common.guardrails import GuardrailScanner
from app.common.logger import Logger
from app.common.model_adapter import ModelAdapter
from app.common.model_adapter_factory import ModelAdapterFactory
from app.common.response import ResponseBuilder
from app.config import Config
from app.helper.schema import SchemaHelper
from app.urls.agent_run import AgentRunRouter
from app.urls.base import BaseRouter
from app.urls.document import DocumentRouter
from app.urls.draft import DraftRouter
from app.urls.eval import EvalRouter
from app.urls.frontend import FrontendRouter
from app.urls.health import HealthRouter
from app.urls.ticket import TicketRouter
from app.urls.tool_action import ToolActionRouter
from app.urls.triage import TriageRouter


class Application:
    """Creates the FastAPI app and mounts routers. Holds no business logic."""

    TITLE = "TrustDesk"
    VERSION = "0.1.0"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._logger = Logger("trustdesk")
        self._database = Database(config)
        self._auth = AuthDependency(config)
        self._model_adapter: ModelAdapter = ModelAdapterFactory().create(config)
        self._guardrails = GuardrailScanner(
            secrets=[config.token, config.model_api_key],
            prompt_markers=self._model_adapter.prompt_markers,
        )

    @property
    def config(self) -> Config:
        return self._config

    @property
    def database(self) -> Database:
        return self._database

    @property
    def model_adapter(self) -> ModelAdapter:
        """The adapter chosen by ``MODEL_PROVIDER``; injected into AI helpers."""
        return self._model_adapter

    @property
    def guardrails(self) -> GuardrailScanner:
        return self._guardrails

    def create_app(self) -> FastAPI:
        app = FastAPI(title=self.TITLE, version=self.VERSION, lifespan=self._lifespan)
        ExceptionHandlerRegistry(self._logger, ResponseBuilder()).register(app)
        self.register_routers(app)
        return app

    def register_routers(self, app: FastAPI) -> None:
        for router in self._routers():
            app.include_router(router.build())

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI) -> AsyncIterator[None]:
        """On server start, make sure the tables exist (data is loaded by ``app.seed``)."""
        with self._database.session_scope() as db:
            SchemaHelper(db).init_schema()
        yield

    def _routers(self) -> list[BaseRouter]:
        return [
            HealthRouter(self._database, self._logger, tags=["health"]),
            FrontendRouter(self._database, self._logger, Config.FRONTEND_PAGE, tags=["frontend"]),
            TicketRouter(
                self._database, self._logger, prefix="/tickets", tags=["tickets"], auth=self._auth
            ),
            TriageRouter(
                self._database,
                self._logger,
                self._model_adapter,
                self._guardrails,
                prefix="/tickets",
                tags=["triage"],
                auth=self._auth,
            ),
            DraftRouter(
                self._database,
                self._logger,
                self._model_adapter,
                self._guardrails,
                prefix="/tickets",
                tags=["drafts"],
                auth=self._auth,
            ),
            ToolActionRouter(
                self._database,
                self._logger,
                self._guardrails,
                self._auth,
                prefix="/tool-actions",
                tags=["tool-actions"],
            ),
            EvalRouter(
                self._database,
                self._logger,
                self._model_adapter,
                self._guardrails,
                prefix="/eval-runs",
                tags=["eval-runs"],
                auth=self._auth,
            ),
            AgentRunRouter(
                self._database,
                self._logger,
                prefix="/agent-runs",
                tags=["agent-runs"],
                auth=self._auth,
            ),
            DocumentRouter(
                self._database,
                self._logger,
                prefix="/documents",
                tags=["documents"],
                auth=self._auth,
            ),
        ]
