from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, EnumColumn, TableNames
from app.models.enums import ApprovalDecision
from app.models.tool_action import ToolActionRequest


class Approval(BaseModel):
    action_id: Mapped[int] = mapped_column(
        ForeignKey(TableNames.column("ToolActionRequest", "id")), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[ApprovalDecision] = mapped_column(EnumColumn.of(ApprovalDecision))
    reason: Mapped[str] = mapped_column(Text, default="")

    action: Mapped[ToolActionRequest] = relationship(ToolActionRequest, lazy="select")
