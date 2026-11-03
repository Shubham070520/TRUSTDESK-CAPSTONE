from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, EnumColumn, TableNames
from app.models.enums import DraftStatus


class Draft(BaseModel):
    """A generated reply. Its public id is ``uuid`` (the ``draft_id`` of the API)."""

    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Ticket", "ticket_id")), index=True
    )
    status: Mapped[DraftStatus] = mapped_column(
        EnumColumn.of(DraftStatus), default=DraftStatus.GENERATED
    )
    body: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list)
