"""Importing this package registers every table on ``Base.metadata``."""
from app.models.agent_run import AgentRun
from app.models.approval import Approval
from app.models.base import Base, BaseModel, EnumColumn, TableNames
from app.models.customer import Customer
from app.models.document import Document
from app.models.draft import Draft
from app.models.enums import ActionStatus, ApprovalDecision, DraftStatus, RunType
from app.models.eval_case import EvalCase
from app.models.eval_run import EvalRun
from app.models.order import Order
from app.models.replacement_order import ReplacementOrder
from app.models.ticket import Ticket
from app.models.ticket_label import TicketLabel
from app.models.tool import Tool
from app.models.tool_action import ToolActionRequest

__all__ = [
    "ActionStatus",
    "AgentRun",
    "Approval",
    "ApprovalDecision",
    "Base",
    "BaseModel",
    "Customer",
    "Document",
    "Draft",
    "DraftStatus",
    "EnumColumn",
    "EvalCase",
    "EvalRun",
    "Order",
    "ReplacementOrder",
    "RunType",
    "TableNames",
    "Ticket",
    "TicketLabel",
    "Tool",
    "ToolActionRequest",
]
