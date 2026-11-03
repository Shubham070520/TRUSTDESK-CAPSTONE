from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TableNames


class ReplacementOrder(BaseModel):
    """Mock fulfilment record. One per executed action, enforced by a unique FK."""

    action_id: Mapped[int] = mapped_column(
        ForeignKey(TableNames.column("ToolActionRequest", "id")), unique=True
    )
    source_order_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Order", "order_id")), index=True
    )
    sku: Mapped[str] = mapped_column(String(64))
