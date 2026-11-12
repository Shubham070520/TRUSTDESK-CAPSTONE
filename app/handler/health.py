from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.health import HealthHelper


class HealthHandler(BaseHandler):
    def __init__(self, helper: HealthHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def check(self) -> JSONResponse:
        return self.execute(self._helper.check, SuccessConfig.HEALTH_OK)
