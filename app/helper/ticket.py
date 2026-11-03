from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.common.exceptions import NotFoundError
from app.helper.base import BaseHelper
from app.models.customer import Customer
from app.models.draft import Draft
from app.models.order import Order
from app.models.ticket import Ticket


@dataclass(frozen=True)
class TicketDetail:
    ticket: Ticket
    customer: Customer
    order: Order | None
    latest_draft: Draft | None


class TicketHelper(BaseHelper):
    """Reads tickets with their customer and order context.

    Never touches ``TicketLabel``: seed expectations are for evaluation only.
    """

    def list_tickets(
        self, status: str | None, page: int, page_size: int
    ) -> tuple[list[Ticket], int]:
        """One page of tickets (oldest id first) and the total matching count."""
        conditions = [Ticket.is_deleted.is_(False)]
        if status is not None:
            conditions.append(Ticket.status == status)
        with self._guard():
            total = int(
                self.db.execute(select(func.count(Ticket.id)).where(*conditions)).scalar_one()
            )
            tickets = list(
                self.db.execute(
                    select(Ticket)
                    .where(*conditions)
                    .order_by(Ticket.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).scalars()
            )
        return tickets, total

    def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        """The ticket with customer, order and latest draft, or ``NotFoundError``."""
        with self._guard():
            ticket = self.db.execute(
                select(Ticket)
                .options(joinedload(Ticket.customer), joinedload(Ticket.order))
                .where(Ticket.ticket_id == ticket_id, Ticket.is_deleted.is_(False))
            ).scalar_one_or_none()
            if ticket is None:
                raise NotFoundError(details={"ticket_id": ticket_id})
            draft = self.db.execute(
                select(Draft)
                .where(Draft.ticket_id == ticket_id, Draft.is_deleted.is_(False))
                .order_by(Draft.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        return TicketDetail(
            ticket=ticket, customer=ticket.customer, order=ticket.order, latest_draft=draft
        )
