from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TableNames
from app.models.customer import Customer


class Order(BaseModel):
    order_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Customer", "customer_id")), index=True
    )
    status: Mapped[str] = mapped_column(String(32))
    placed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    eligible_return_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    total: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    payment_status: Mapped[str] = mapped_column(String(32))
    tracking_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    customer: Mapped[Customer] = relationship(Customer, lazy="select")
