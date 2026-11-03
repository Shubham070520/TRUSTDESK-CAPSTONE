from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.exception_handlers import ExceptionHandlerRegistry
from app.common.logger import Logger
from app.common.response import ResponseBuilder
from app.config import Config
from app.helper.schema import SchemaHelper
from app.urls.base import BaseRouter
from app.urls.document import DocumentRouter
from app.urls.health import HealthRouter
from app.urls.ticket import TicketRouter


class Application:
    """Creates the FastAPI app and mounts routers. Holds no business logic."""

    TITLE = "TrustDesk"
    VERSION = "0.1.0"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._logger = Logger("trustdesk")
        self._database = Database(config)
        self._auth = AuthDependency(config)

    @property
    def config(self) -> Config:
        return self._config

    @property
    def database(self) -> Database:
        return self._database

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
            TicketRouter(
                self._database, self._logger, prefix="/tickets", tags=["tickets"], auth=self._auth
            ),
            DocumentRouter(
                self._database,
                self._logger,
                prefix="/documents",
                tags=["documents"],
                auth=self._auth,
            ),
        ]
