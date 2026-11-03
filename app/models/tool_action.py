from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, EnumColumn, TableNames
from app.models.enums import ActionStatus


class ToolActionRequest(BaseModel):
    """A requested tool action. Its public id is ``uuid`` (the ``action_id`` of the API).

    ``idempotency_key`` is unique so a retry can never create a second action.
    """

    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Ticket", "ticket_id")), index=True
    )
    tool_name: Mapped[str] = mapped_column(
        String(64), ForeignKey(TableNames.column("Tool", "tool_name"))
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(16))
    requires_human_approval: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[ActionStatus] = mapped_column(
        EnumColumn.of(ActionStatus), default=ActionStatus.APPROVAL_REQUIRED, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
