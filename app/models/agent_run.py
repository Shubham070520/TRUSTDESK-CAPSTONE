from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, EnumColumn, TableNames
from app.models.enums import RunType


class AgentRun(BaseModel):
    """Minimal trace of one AI run. Its public id is ``uuid`` (the ``run_id`` of the API)."""

    ticket_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey(TableNames.column("Ticket", "ticket_id")), nullable=True, index=True
    )
    run_type: Mapped[RunType] = mapped_column(EnumColumn.of(RunType), index=True)
    status: Mapped[str] = mapped_column(String(32))
    retrieved_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list[Any]] = mapped_column(JSON, default=list)
    guardrail_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
