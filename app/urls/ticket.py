from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.schema import Envelope, TicketDetailData, TicketListData
from app.config import Config
from app.handler.ticket import TicketHandler
from app.helper.ticket import TicketHelper
from app.urls.base import BaseRouter


class TicketRouter(BaseRouter):
    def register_routes(self) -> None:
        self._router.add_api_route(
            "",
            self._list,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[TicketListData],
            dependencies=self._secured(),
            summary="List tickets (paginated, optional status filter)",
        )
        self._router.add_api_route(
            "/{ticket_id}",
            self._get,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[TicketDetailData],
            dependencies=self._secured(),
            summary="Ticket with customer, order, latest triage and latest draft",
        )

    def _build_handler(self, db: Session) -> TicketHandler:
        return TicketHandler(TicketHelper(db), self._logger)

    def _list(
        self,
        status: str | None = None,
        page: int = Config.DEFAULT_PAGE,
        page_size: int = Config.DEFAULT_PAGE_SIZE,
    ) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).list_tickets(status, page, page_size)

    def _get(self, ticket_id: str) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).get_ticket(ticket_id)
