from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.common.schema import AgentRunOut
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.agent_run import AgentRunHelper


class AgentRunHandler(BaseHandler):
    def __init__(self, helper: AgentRunHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def get_run(self, run_id: str) -> JSONResponse:
        return self.execute(partial(self._get, run_id), SuccessConfig.AGENT_RUN_FETCHED)

    def _get(self, run_id: str) -> dict[str, Any]:
        run = self._helper.get(self.validate_uuid(run_id))
        return AgentRunOut.model_validate(run).model_dump(mode="json")
