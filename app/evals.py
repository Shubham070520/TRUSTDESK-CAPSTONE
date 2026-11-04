"""Evaluation command: ``python -m app.evals``.

A command-line entry point (like ``app.seed``), not part of the request flow. It runs
every case, stores the run and writes the report. It exits with 1 if any case fails.
"""
import sys
from pathlib import Path

from app import Application
from app.common.eval_report import EvalReportWriter
from app.common.exceptions import ConflictError
from app.common.logger import Logger
from app.config import Config
from app.handler.eval import EvalHandler
from app.helper.eval import EvalHelper
from app.helper.schema import SchemaHelper


class EvalCommand:
    REPORT_PATH = Config.BASE_DIR / "docs" / "EVAL_REPORT.md"

    def __init__(self, config: Config, logger: Logger, report_path: Path = REPORT_PATH) -> None:
        self._config = config
        self._logger = logger
        self._report_path = report_path

    def run(self) -> int:
        application = Application(self._config)
        try:
            with application.database.session_scope() as db:
                SchemaHelper(db).init_schema()
                helper = EvalHelper.compose(db, application.model_adapter, application.guardrails)
                try:
                    data = EvalHandler.serialize(helper.run())
                except ConflictError:
                    self._logger.error("No eval cases found. Run `python -m app.seed` first.")
                    return 1
        finally:
            application.database.dispose()

        self._report_path.write_text(EvalReportWriter().render(data), encoding="utf-8")
        metrics = data["metrics"]
        passed, total = metrics["passed_cases"], data["total_cases"]
        self._logger.info(f"eval run {data['eval_run_id']}: {passed} of {total} cases passed")
        for name, value in metrics.items():
            if isinstance(value, float):
                self._logger.info(f"{name}: {value:.2f}")
        for entry in metrics["adversarial_summary"]:
            verdict = "safe" if entry["safe"] else "NOT SAFE"
            self._logger.info(f"{entry['case_id']}: {verdict}")
        self._logger.info(f"report written to {self._report_path}")
        return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(EvalCommand(Config.load(), Logger("evals")).run())
