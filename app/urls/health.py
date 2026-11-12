from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.common.schema import Envelope, HealthData
from app.handler.health import HealthHandler
from app.helper.health import HealthHelper
from app.urls.base import BaseRouter


class HealthRouter(BaseRouter):
    def register_routes(self) -> None:
        self._router.add_api_route(
            "/health",
            self._health,
            methods=["GET"],
            status_code=status.HTTP_200_OK,
            response_model=Envelope[HealthData],
            summary="Liveness and database readiness (no auth)",
        )

    def _build_handler(self, db: Session) -> HealthHandler:
        return HealthHandler(HealthHelper(db), self._logger)

    def _health(self) -> Any:
        with self._database.session_scope() as db:
            response: JSONResponse = self._build_handler(db).check()
        return response
