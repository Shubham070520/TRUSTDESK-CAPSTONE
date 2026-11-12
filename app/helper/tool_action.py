import re
from dataclasses import dataclass
from typing import Any, ClassVar

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictError,
    DatabaseError,
    GuardrailError,
    ToolExecutionError,
    ToolNotEnabledError,
    ValidationError,
)
from app.common.guardrails import GuardrailResult, GuardrailScanner
from app.common.ticket_signals import TicketSignals
from app.helper.agent_run import AgentRunHelper
from app.helper.base import BaseHelper
from app.helper.ticket import TicketDetail, TicketHelper
from app.models.approval import Approval
from app.models.enums import ActionStatus, ApprovalDecision, RunStatus, RunType
from app.models.order import Order
from app.models.replacement_order import ReplacementOrder
from app.models.ticket import Ticket
from app.models.tool import Tool
from app.models.tool_action import ToolActionRequest


@dataclass(frozen=True)
class ToolActionOutcome:
    """``replayed`` means nothing changed: a retry or repeat got the stored state back."""

    action: ToolActionRequest
    approval: Approval | None
    run_id: str | None
    replayed: bool


class ToolActionHelper(BaseHelper):
    """The approval-gated action: request, then a human decision, then execute.

    Requests are validated here on their own, whether or not the action was
    recommended. Execution needs an ``approved`` status, which only a human decision
    can set, so the catalog cannot switch the gate off. A disabled tool is refused at
    every step, so a row that reached the table some other way still cannot run. Status
    changes are conditional updates, so parallel calls cannot both win. Each change and
    its audit row share a commit. Refused calls and replays write nothing.

    A retry is matched by its key straight after the shape checks, so it gets the
    stored action (or a conflict) even if the ticket or order changed since.
    """

    ENABLED_TOOL: ClassVar[str] = "create_replacement_order"

    _FIELD_LIMITS: ClassVar[dict[str, int]] = {
        "order_id": 32,
        "sku": 64,
        "reason": 500,
        "idempotency_key": 128,
    }
    _KEY: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]*$")

    def __init__(
        self,
        db: Session,
        tickets: TicketHelper,
        runs: AgentRunHelper,
        guardrails: GuardrailScanner,
    ) -> None:
        super().__init__(db)
        self._tickets = tickets
        self._runs = runs
        self._guardrails = guardrails

    # ---- request ----------------------------------------------------------

    def request(
        self, ticket_id: str, tool_name: str, payload: dict[str, Any], actor: str
    ) -> ToolActionOutcome:
        tool = self._require_enabled_tool(tool_name)
        self._check_fields(tool, payload)
        key = payload["idempotency_key"]

        existing = self._find_by_key(key)
        if existing is not None:
            return self._replay(existing, ticket_id, tool_name, payload)

        detail = self._tickets.get_ticket_detail(ticket_id)
        self._check_category(detail.ticket, tool)
        self._check_order_and_item(detail, payload)
        scan = self._check_not_escalated(detail)

        action = ToolActionRequest(
            ticket_id=ticket_id,
            tool_name=tool_name,
            payload=payload,
            risk_level=tool.risk_level,
            requires_human_approval=True,
            status=ActionStatus.APPROVAL_REQUIRED,
            idempotency_key=key,
        )
        try:
            self.db.add(action)
            self.db.flush()
        except IntegrityError as exc:
            self.rollback()
            winner = self._find_by_key(key)
            if winner is None:
                raise DatabaseError() from exc
            return self._replay(winner, ticket_id, tool_name, payload)
        run_id = self._audit(action, "requested", actor, {"input": scan.to_dict()})
        self.commit()
        return ToolActionOutcome(action, None, run_id, False)

    def _require_enabled_tool(self, tool_name: str) -> Tool:
        with self._guard():
            tool = self.db.execute(
                select(Tool).where(Tool.tool_name == tool_name, Tool.is_deleted.is_(False))
            ).scalar_one_or_none()
        if tool is None:
            raise ValidationError(details={"tool_name": tool_name, "reason": "unknown_tool"})
        if tool_name != self.ENABLED_TOOL:
            raise ToolNotEnabledError(details={"tool_name": tool_name})
        return tool

    def _check_fields(self, tool: Tool, payload: dict[str, Any]) -> None:
        missing = [
            name
            for name in tool.required_fields
            if not isinstance(payload.get(name), str) or not payload[name].strip()
        ]
        if missing:
            raise ValidationError(details={"reason": "missing_fields", "fields": missing})
        unexpected = sorted(set(payload) - set(tool.required_fields))
        if unexpected:
            raise ValidationError(details={"reason": "unexpected_fields", "fields": unexpected})
        too_long = [
            name
            for name, limit in self._FIELD_LIMITS.items()
            if name in payload and len(payload[name]) > limit
        ]
        if too_long:
            raise ValidationError(details={"reason": "field_too_long", "fields": too_long})
        if not self._KEY.match(payload["idempotency_key"]):
            raise ValidationError(details={"reason": "invalid_idempotency_key"})

    def _replay(
        self,
        existing: ToolActionRequest,
        ticket_id: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> ToolActionOutcome:
        same = (
            existing.ticket_id == ticket_id
            and existing.tool_name == tool_name
            and existing.payload == payload
        )
        if not same:
            raise ConflictError(
                details={
                    "reason": "idempotency_key_reused",
                    "idempotency_key": existing.idempotency_key,
                }
            )
        return ToolActionOutcome(existing, self._latest_approval(existing), None, True)

    @staticmethod
    def _check_category(ticket: Ticket, tool: Tool) -> None:
        if ticket.triage_category is None:
            raise ConflictError(
                details={"reason": "ticket_not_triaged", "ticket_id": ticket.ticket_id}
            )
        if ticket.triage_category not in tool.allowed_categories:
            raise ValidationError(
                details={
                    "reason": "category_not_allowed",
                    "category": ticket.triage_category,
                    "allowed_categories": tool.allowed_categories,
                }
            )

    def _check_order_and_item(self, detail: TicketDetail, payload: dict[str, Any]) -> None:
        order = detail.order
        if order is None or order.order_id != payload["order_id"]:
            raise ValidationError(
                details={"reason": "order_mismatch", "order_id": payload["order_id"]}
            )
        reason = self._item_problem(order, payload["sku"])
        if reason is not None:
            raise ValidationError(details={"reason": reason, "sku": payload["sku"]})

    @staticmethod
    def _item_problem(order: Order, sku: str) -> str | None:
        item = next((entry for entry in order.items if entry["sku"] == sku), None)
        if item is None:
            return "sku_not_on_order"
        if item["final_sale"]:
            return "final_sale"
        return None

    def _check_not_escalated(self, detail: TicketDetail) -> GuardrailResult:
        """An escalated ticket goes to a specialist first, so no replacement can be requested."""
        context = self._tickets.build_context(detail)
        scan = self._guardrails.scan_input(f"{context.subject}\n{context.body}")
        if (
            detail.ticket.triage_escalate
            or scan.flagged
            or TicketSignals.SAFETY.search(TicketSignals.text_of(context))
        ):
            raise GuardrailError(
                details={"reason": "ticket_escalated", "ticket_id": context.ticket_id}
            )
        return scan

    # ---- human decision ---------------------------------------------------

    def decide(
        self, action_id: str, decision: ApprovalDecision, reason: str, actor: str
    ) -> ToolActionOutcome:
        action = self._get_enabled(action_id)
        target = (
            ActionStatus.APPROVED
            if decision is ApprovalDecision.APPROVED
            else ActionStatus.REJECTED
        )
        if not self._transition(action, ActionStatus.APPROVAL_REQUIRED, target):
            latest = self._latest_approval(action)
            if latest is not None and latest.decision is decision:
                return ToolActionOutcome(action, latest, None, True)
            raise ConflictError(
                details={"reason": "already_decided", "status": action.status.value}
            )
        approval = Approval(
            action_id=action.id, reviewer_id=actor, decision=decision, reason=reason
        )
        with self._guard():
            self.db.add(approval)
        run_id = self._audit(action, decision.value, actor, {})
        self.commit()
        return ToolActionOutcome(action, approval, run_id, False)

    # ---- execute ----------------------------------------------------------

    def execute(self, action_id: str, actor: str) -> ToolActionOutcome:
        action = self._get_enabled(action_id)
        if not self._transition(action, ActionStatus.APPROVED, ActionStatus.EXECUTED):
            return self._not_executable(action)
        try:
            replacement = self._fulfil(action)
        except ToolExecutionError as exc:
            return self._record_failure(action, actor, exc.details["reason"])
        except SQLAlchemyError:
            return self._record_failure(action, actor, "fulfilment_error")
        action.result = {
            "replacement_id": replacement.uuid,
            "source_order_id": replacement.source_order_id,
            "sku": replacement.sku,
        }
        run_id = self._audit(action, "executed", actor, {})
        self.commit()
        return ToolActionOutcome(action, self._latest_approval(action), run_id, False)

    def _fulfil(self, action: ToolActionRequest) -> ReplacementOrder:
        """Mock fulfilment: one row per action. The order is checked again, as it may have changed."""
        order_id, sku = action.payload["order_id"], action.payload["sku"]
        order = self.db.execute(
            select(Order).where(Order.order_id == order_id, Order.is_deleted.is_(False))
        ).scalar_one_or_none()
        if order is None:
            raise ToolExecutionError(details={"reason": "order_not_found"})
        problem = self._item_problem(order, sku)
        if problem is not None:
            raise ToolExecutionError(details={"reason": problem})
        replacement = ReplacementOrder(action_id=action.id, source_order_id=order_id, sku=sku)
        self.db.add(replacement)
        self.db.flush()
        return replacement

    def _not_executable(self, action: ToolActionRequest) -> ToolActionOutcome:
        if action.status is ActionStatus.EXECUTED:
            return ToolActionOutcome(action, self._latest_approval(action), None, True)
        details: dict[str, Any] = {"reason": "not_approved", "status": action.status.value}
        if action.status is ActionStatus.FAILED:
            details = {"reason": "execution_failed", "status": action.status.value}
            details["error"] = (action.result or {}).get("error")
        raise ConflictError(details=details)

    def _record_failure(
        self, action: ToolActionRequest, actor: str, error: str
    ) -> ToolActionOutcome:
        """Undo the attempt, then keep the error on the action in its own commit."""
        self.rollback()
        if not self._transition(action, ActionStatus.APPROVED, ActionStatus.FAILED):
            return self._not_executable(action)
        action.result = {"error": error}
        run_id = self._audit(action, "failed", actor, {"error": error}, RunStatus.FAILED)
        self.commit()
        raise ToolExecutionError(
            details={
                "action_id": action.uuid,
                "status": ActionStatus.FAILED.value,
                "error": error,
                "run_id": run_id,
            }
        )

    # ---- shared -----------------------------------------------------------

    def _get_enabled(self, action_id: str) -> ToolActionRequest:
        action = self.get_by_uuid(ToolActionRequest, action_id)
        if action.tool_name != self.ENABLED_TOOL:
            raise ToolNotEnabledError(details={"tool_name": action.tool_name})
        return action

    def _transition(
        self, action: ToolActionRequest, source: ActionStatus, target: ActionStatus
    ) -> bool:
        """Move the status only if it is still ``source``. Only one parallel caller can win."""
        with self._guard():
            result = self.db.execute(
                update(ToolActionRequest)
                .where(ToolActionRequest.id == action.id, ToolActionRequest.status == source)
                .values(status=target)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 1:
                self.db.refresh(action)
                return True
        self.rollback()  # releases the write lock; ``action`` reloads on next use
        return False

    def _find_by_key(self, key: str) -> ToolActionRequest | None:
        with self._guard():
            return self.db.execute(
                select(ToolActionRequest).where(ToolActionRequest.idempotency_key == key)
            ).scalar_one_or_none()

    def _latest_approval(self, action: ToolActionRequest) -> Approval | None:
        with self._guard():
            return self.db.execute(
                select(Approval)
                .where(Approval.action_id == action.id)
                .order_by(Approval.id.desc())
                .limit(1)
            ).scalar_one_or_none()

    def _audit(
        self,
        action: ToolActionRequest,
        event: str,
        actor: str,
        guardrail_results: dict[str, Any],
        status: RunStatus = RunStatus.COMPLETED,
    ) -> str:
        """One audit row per change, in the same commit as the change."""
        run = self._runs.create(
            ticket_id=action.ticket_id,
            run_type=RunType.TOOL_RECOMMENDATION,
            status=status,
            guardrail_results=guardrail_results,
            tool_calls=[
                {
                    "tool_name": action.tool_name,
                    "action_id": action.uuid,
                    "idempotency_key": action.idempotency_key,
                    "event": event,
                    "actor": actor,
                    "status": action.status.value,
                }
            ],
        )
        return run.uuid
