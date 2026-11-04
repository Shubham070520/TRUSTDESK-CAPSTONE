import re
import unicodedata
from datetime import date, datetime
from typing import ClassVar

from app.common.guardrail_rules import GuardrailRules
from app.common.model_adapter import TicketContext


class TicketSignals:
    """Facts read from a ticket's wording and dates, shared by the mock and the action rules.

    Action rules use these rather than model output, so what may be recommended
    does not depend on which model is configured. Keyword based and English only.
    Nothing here reads the current time: windows are judged from the ticket itself.
    """

    SAFETY: ClassVar[re.Pattern[str]] = re.compile(
        r"\bswell|\bswollen\b|overheat|burning smell|exposed wire|electric shock|\bsmok(e|ing)\b"
        r"|caught fire"
    )
    DAMAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"\bdamaged?\b|\bcracked\b|\bbroken\b|\bshattered\b"
    )
    DEFECT: ClassVar[re.Pattern[str]] = re.compile(
        r"\bdefect|\bfaulty\b|malfunction|stopped working|(not|isn.?t|doesn.?t) work"
    )
    STALE_TRACKING: ClassVar[re.Pattern[str]] = re.compile(
        r"no movement|(not|hasn.?t|has not) (been )?(moved|updated)|\bstuck\b"
    )
    DUPLICATE_CHARGE: ClassVar[re.Pattern[str]] = re.compile(
        r"(charged|billed) (me )?(twice|two times)|(double|duplicate) (charge|payment)"
        r"|two (charges|payments)"
    )
    COUPON: ClassVar[re.Pattern[str]] = re.compile(r"\bcoupons?\b|\bvouchers?\b")
    ACCOUNT_LOCK: ClassVar[re.Pattern[str]] = re.compile(r"\block\s+(?:\w+\s+){0,2}account\b")

    @staticmethod
    def text_of(ticket: TicketContext) -> str:
        """Subject and body, with look-alike and invisible characters folded away."""
        text = unicodedata.normalize("NFKC", f"{ticket.subject}\n{ticket.body}")
        return GuardrailRules.ZERO_WIDTH.sub("", text).casefold()

    @staticmethod
    def inside_return_window(ticket: TicketContext) -> bool:
        """Compares the ticket's own date with the order's last return day."""
        if ticket.order is None or not ticket.order.eligible_return_until:
            return False
        try:
            opened = datetime.fromisoformat(ticket.opened_at).date()
            last_day = date.fromisoformat(ticket.order.eligible_return_until)
        except ValueError:
            return False
        return opened <= last_day
