"""Pydantic schemas used by routers and handlers.

Every API schema lives in this module. Add new request and response
schemas here rather than next to the router that uses them.

Note on names: the API exposes the source ``created_at`` of tickets and
customers. In the database these are ``Ticket.opened_at`` and
``Customer.customer_since``, so the schemas map them with a validation alias.
"""
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.config import Config

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """The single response shape used by every endpoint.

    Success: {"success": true,  "message": "...", "data": ...}
    Error:   {"success": false, "message": "...", "error_code": 1xxx, "data": {}}
    """

    success: bool
    message: str
    data: T | None = None
    error_code: int | None = None


class OrmSchema(BaseModel):
    """Base for schemas built from ORM objects."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---- health ---------------------------------------------------------------


class HealthData(BaseModel):
    status: str
    database: str


# ---- tickets --------------------------------------------------------------


class CustomerOut(OrmSchema):
    customer_id: str
    name: str
    email: str
    tier: str
    country: str
    created_at: str = Field(validation_alias="customer_since")
    verified: bool
    tags: list[str]


class OrderOut(OrmSchema):
    order_id: str
    customer_id: str
    status: str
    placed_at: date | None
    delivered_at: date | None
    eligible_return_until: date | None
    total: float
    currency: str
    payment_status: str
    tracking_number: str | None
    items: list[dict[str, Any]]


class TicketOut(OrmSchema):
    ticket_id: str
    customer_id: str
    order_id: str | None
    channel: str
    subject: str
    body: str
    created_at: str = Field(validation_alias="opened_at")
    status: str


class TriageOut(BaseModel):
    category: str | None
    priority: str | None
    sentiment: str | None
    should_escalate: bool | None
    reason_summary: str | None
    run_id: str | None


class TicketListItem(TicketOut):
    triage: TriageOut | None = None


class DraftOut(OrmSchema):
    draft_id: str = Field(validation_alias="uuid")
    ticket_id: str
    status: str
    body: str
    citations: list[Any]
    created_at: datetime


class TicketListData(BaseModel):
    items: list[TicketListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class TicketDetailData(BaseModel):
    ticket: TicketOut
    customer: CustomerOut
    order: OrderOut | None
    latest_triage: TriageOut | None
    latest_draft: DraftOut | None


# ---- documents ------------------------------------------------------------


class DocumentIngestItem(BaseModel):
    doc_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-]{2,63}$")
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200_000)
    source_path: str | None = Field(default=None, max_length=500)
    version: str = Field(default=Config.DEFAULT_DOC_VERSION, min_length=1, max_length=32)
    audience: str = Field(default=Config.DEFAULT_DOC_AUDIENCE, min_length=1, max_length=200)


class DocumentIngestRequest(BaseModel):
    documents: list[DocumentIngestItem] = Field(min_length=1, max_length=50)


class DocumentIngestResultItem(BaseModel):
    doc_id: str
    outcome: str


class DocumentIngestData(BaseModel):
    ingested: int
    document_ids: list[str]
    results: list[DocumentIngestResultItem]


class DocumentSearchResult(BaseModel):
    doc_id: str
    title: str
    heading: str
    snippet: str
    score: float
    audience: str


class DocumentSearchData(BaseModel):
    query: str
    results: list[DocumentSearchResult]
