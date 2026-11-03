from abc import ABC, abstractmethod
from typing import Any

from fastapi import APIRouter, Depends

from app.common.auth import AuthDependency
from app.common.database import Database
from app.common.logger import Logger


class BaseRouter(ABC):
    """Holds an APIRouter. Subclasses map paths to handler methods and nothing else.

    Routers are the composition point for one request: they open a session
    from the injected ``Database`` and assemble the handler and helper.
    Pass ``auth`` to protect the routes that use ``self._secured()``.
    """

    def __init__(
        self,
        database: Database,
        logger: Logger,
        prefix: str = "",
        tags: list[str] | None = None,
        auth: AuthDependency | None = None,
    ) -> None:
        self._database = database
        self._logger = logger
        self._auth = auth
        self._router = APIRouter(prefix=prefix, tags=list(tags) if tags else None)
        self._built = False

    @property
    def router(self) -> APIRouter:
        return self._router

    @abstractmethod
    def register_routes(self) -> None:
        """Add this resource's routes to ``self._router``."""

    def build(self) -> APIRouter:
        """Register routes once and return the router for mounting."""
        if not self._built:
            self.register_routes()
            self._built = True
        return self._router

    def _secured(self) -> list[Any]:
        """Route dependencies that enforce the bearer token (none if no auth injected)."""
        return [Depends(self._auth)] if self._auth is not None else []
