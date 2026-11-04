"""Success messages. No inline success strings elsewhere."""
from typing import ClassVar


class SuccessConfig:
    HEALTH_OK: ClassVar[str] = "Service is healthy"
    TICKETS_LISTED: ClassVar[str] = "Tickets retrieved"
    TICKET_FETCHED: ClassVar[str] = "Ticket retrieved"
    DOCUMENTS_SEARCHED: ClassVar[str] = "Documents searched"
    DOCUMENT_FETCHED: ClassVar[str] = "Document retrieved"
    DOCUMENTS_INGESTED: ClassVar[str] = "Documents ingested"
    TICKET_TRIAGED: ClassVar[str] = "Ticket triaged"
    DRAFT_GENERATED: ClassVar[str] = "Draft generated"
    AGENT_RUN_FETCHED: ClassVar[str] = "Agent run retrieved"
    TOOL_ACTION_REQUESTED: ClassVar[str] = "Tool action requested"
    TOOL_ACTION_DECIDED: ClassVar[str] = "Decision recorded"
    TOOL_ACTION_EXECUTED: ClassVar[str] = "Tool action executed"
    EVAL_RUN_COMPLETED: ClassVar[str] = "Evaluation completed"
    EVAL_RUN_FETCHED: ClassVar[str] = "Evaluation run retrieved"
