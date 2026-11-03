from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TableNames
from app.models.customer import Customer
from app.models.order import Order


class Ticket(BaseModel):
    """A support ticket. The customer's message is stored unchanged.

    ``opened_at`` is the source ``created_at`` kept as the original ISO-8601
    string with its timezone offset. Policy windows are judged from it.
    Seed expectations live in ``TicketLabel``, never here.
    """

    ticket_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(TableNames.column("Customer", "customer_id")), index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey(TableNames.column("Order", "order_id")),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), index=True)

    # Filled by the triage step. Never overwritten by re-seeding.
    triage_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_escalate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    triage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customer: Mapped[Customer] = relationship(Customer, lazy="select")
    order: Mapped[Order | None] = relationship(Order, lazy="select")
