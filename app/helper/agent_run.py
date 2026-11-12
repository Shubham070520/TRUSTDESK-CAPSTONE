from typing import Any

from app.helper.base import BaseHelper
from app.models.agent_run import AgentRun
from app.models.enums import RunStatus, RunType


class AgentRunHelper(BaseHelper):
    """Writes and reads the minimal trace of each AI run."""

    def create(
        self,
        ticket_id: str | None,
        run_type: RunType,
        status: RunStatus,
        guardrail_results: dict[str, Any],
        retrieved_doc_ids: list[str] | None = None,
        tool_calls: list[Any] | None = None,
    ) -> AgentRun:
        """Add a run and assign its id. The caller commits, so it can share a transaction."""
        run = AgentRun(
            ticket_id=ticket_id,
            run_type=run_type,
            status=status.value,
            retrieved_doc_ids=retrieved_doc_ids or [],
            tool_calls=tool_calls or [],
            guardrail_results=guardrail_results,
        )
        with self._guard():
            self.db.add(run)
            self.db.flush()
        return run

    def get(self, run_id: str) -> AgentRun:
        return self.get_by_uuid(AgentRun, run_id)
