from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.common.schema import EvalRunData, EvalRunRequest
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.eval import EvalHelper
from app.models.eval_run import EvalRun


class EvalHandler(BaseHandler):
    def __init__(self, helper: EvalHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def run(self, body: EvalRunRequest | None) -> JSONResponse:
        return self.execute(partial(self._run, body), SuccessConfig.EVAL_RUN_COMPLETED)

    def get_run(self, eval_run_id: str) -> JSONResponse:
        return self.execute(partial(self._get, eval_run_id), SuccessConfig.EVAL_RUN_FETCHED)

    # ---- actions run inside ``execute`` -----------------------------------

    def _run(self, body: EvalRunRequest | None) -> dict[str, Any]:
        case_ids = body.case_ids if body is not None else None
        return self.serialize(self._helper.run(case_ids))

    def _get(self, eval_run_id: str) -> dict[str, Any]:
        return self.serialize(self._helper.get(self.validate_uuid(eval_run_id)))

    @staticmethod
    def serialize(run: EvalRun) -> dict[str, Any]:
        data = EvalRunData(
            eval_run_id=run.uuid,
            started_at=run.started_at,
            completed_at=run.completed_at,
            total_cases=run.total_cases,
            metrics=run.metrics,
            case_results=run.case_results,
        )
        return data.model_dump(mode="json")
