import math
from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.logger import Logger
from app.common.schema import (
    CustomerOut,
    DraftOut,
    OrderOut,
    TicketDetailData,
    TicketListData,
    TicketListItem,
    TicketOut,
    TriageOut,
)
from app.config import SuccessConfig
from app.handler.base import BaseHandler
from app.helper.ticket import TicketHelper
from app.models.ticket import Ticket


class TicketHandler(BaseHandler):
    def __init__(self, helper: TicketHelper, logger: Logger) -> None:
        super().__init__(logger)
        self._helper = helper

    def list_tickets(self, status: str | None, page: int, page_size: int) -> JSONResponse:
        return self.execute(
            partial(self._list, status, page, page_size), SuccessConfig.TICKETS_LISTED
        )

    def get_ticket(self, ticket_id: str) -> JSONResponse:
        return self.execute(partial(self._detail, ticket_id), SuccessConfig.TICKET_FETCHED)

    # ---- actions run inside ``execute`` -----------------------------------

    def _list(self, status: str | None, page: int, page_size: int) -> dict[str, Any]:
        page, page_size = self.validate_pagination(page, page_size)
        if status is not None:
            status = self.validate_identifier(status, "status")
        tickets, total = self._helper.list_tickets(status, page, page_size)
        items = []
        for ticket in tickets:
            item = TicketListItem.model_validate(ticket)
            item.triage = self._triage_of(ticket)
            items.append(item)
        data = TicketListData(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )
        return data.model_dump(mode="json")

    def _detail(self, ticket_id: str) -> dict[str, Any]:
        ticket_id = self.validate_identifier(ticket_id, "ticket_id")
        detail = self._helper.get_ticket_detail(ticket_id)
        data = TicketDetailData(
            ticket=TicketOut.model_validate(detail.ticket),
            customer=CustomerOut.model_validate(detail.customer),
            order=OrderOut.model_validate(detail.order) if detail.order else None,
            latest_triage=self._triage_of(detail.ticket),
            latest_draft=(
                DraftOut.model_validate(detail.latest_draft) if detail.latest_draft else None
            ),
        )
        return data.model_dump(mode="json")

    @staticmethod
    def _triage_of(ticket: Ticket) -> TriageOut | None:
        """Triage result stored on the ticket, or ``None`` if triage has not run."""
        if ticket.triage_category is None:
            return None
        return TriageOut(
            category=ticket.triage_category,
            priority=ticket.triage_priority,
            sentiment=ticket.triage_sentiment,
            should_escalate=ticket.triage_escalate,
            reason_summary=ticket.triage_reason,
            run_id=ticket.triage_run_id,
        )
