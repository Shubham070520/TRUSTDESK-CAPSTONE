"""Success messages. No inline success strings elsewhere."""
from typing import ClassVar


class SuccessConfig:
    HEALTH_OK: ClassVar[str] = "Service is healthy"
    TICKETS_LISTED: ClassVar[str] = "Tickets retrieved"
    TICKET_FETCHED: ClassVar[str] = "Ticket retrieved"
    DOCUMENTS_SEARCHED: ClassVar[str] = "Documents searched"
    DOCUMENTS_INGESTED: ClassVar[str] = "Documents ingested"
