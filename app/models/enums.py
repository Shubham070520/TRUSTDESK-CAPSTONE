from enum import Enum


class DraftStatus(str, Enum):
    GENERATED = "generated"
    EDITED = "edited"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class ActionStatus(str, Enum):
    REQUESTED = "requested"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class RunType(str, Enum):
    TRIAGE = "triage"
    DRAFT_REPLY = "draft_reply"
    TOOL_RECOMMENDATION = "tool_recommendation"
    EVAL_CASE = "eval_case"
