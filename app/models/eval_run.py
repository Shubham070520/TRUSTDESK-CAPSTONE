from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class EvalRun(BaseModel):
    """A stored evaluation summary. Its public id is ``uuid`` (the ``eval_run_id``)."""

    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    case_results: Mapped[list[Any]] = mapped_column(JSON, default=list)
