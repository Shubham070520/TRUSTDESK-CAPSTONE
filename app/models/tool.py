from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Tool(BaseModel):
    """An entry of the tool catalog (``tool_actions.json``)."""

    tool_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16))
    requires_human_approval: Mapped[bool] = mapped_column(Boolean)
    allowed_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_amount_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
