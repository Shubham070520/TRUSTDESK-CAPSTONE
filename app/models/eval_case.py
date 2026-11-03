from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TableNames


class EvalCase(BaseModel):
    """An evaluation case from ``eval_cases.jsonl``. For evaluation only."""

    case_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Ticket", "ticket_id")), index=True
    )
    input: Mapped[str] = mapped_column(Text)
    expected: Mapped[dict[str, Any]] = mapped_column(JSON)
