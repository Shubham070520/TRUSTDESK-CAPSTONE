from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TableNames


class TicketLabel(BaseModel):
    """Seed expectations for a ticket. For evaluation only.

    The AI path must never read this table.
    """

    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Ticket", "ticket_id")), unique=True
    )
    expected_category: Mapped[str] = mapped_column(String(32))
    expected_priority: Mapped[str] = mapped_column(String(32))
    expected_sentiment: Mapped[str] = mapped_column(String(32))
    expected_escalation: Mapped[bool] = mapped_column(Boolean)
    expected_actions: Mapped[list[Any]] = mapped_column(JSON, default=list)
