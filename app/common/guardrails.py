import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable

from app.common.guardrail_rules import GuardrailReason, GuardrailRules, Rule
from app.config import Config


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of one scan.

    For input and document scans ``flagged`` means "unsafe or suspicious".
    For output checks it means "blocked". ``evidence`` holds a short snippet
    per reason so a reviewer can see why, without storing the whole message.
    """

    flagged: bool
    reasons: tuple[GuardrailReason, ...] = ()
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def safe(self) -> bool:
        return not self.flagged

    def has(self, reason: GuardrailReason) -> bool:
        return reason in self.reasons

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form for traces."""
        return {
            "flagged": self.flagged,
            "reasons": [reason.value for reason in self.reasons],
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ScannableDocument:
    """What the scanner needs to judge a retrieved document."""

    doc_id: str
    audience: str
    text: str


class GuardrailScanner:
    """Checks untrusted input, retrieved documents, and model output.

    Pure logic with no I/O, so it is cheap to inject and to test. Known
    secrets (the API token, the model key) are passed in so the output
    filter can recognise them exactly.

    Limits: pattern based. Paraphrases and non-English text can slip past
    ``scan_input``; the action layer does not depend on it for safety.

    ``prompt_markers`` are phrases from the model's real prompts. Output holding
    one is a prompt leak, whatever the sentence around it says.
    """

    _EVIDENCE_CHARS: ClassVar[int] = 80
    _MIN_SECRET_LENGTH: ClassVar[int] = 8
    _SENTENCE_SPLIT: ClassVar[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+|\n+")

    def __init__(
        self,
        secrets: Iterable[str] = (),
        max_coupon_inr: int = Config.MAX_STANDARD_COUPON_INR,
        prompt_markers: Iterable[str] = (),
    ) -> None:
        self._secrets = tuple(s for s in secrets if len(s.strip()) >= self._MIN_SECRET_LENGTH)
        self._max_coupon_inr = max_coupon_inr
        self._prompt_markers = tuple(self._folded(marker) for marker in prompt_markers)

    # ---- public checks ----------------------------------------------------

    def scan_input(self, text: str | None) -> GuardrailResult:
        """Flag prompt injection, secret requests and policy-bypass attempts."""
        normalized = self._normalize(text)
        found: dict[GuardrailReason, str] = {}
        self._apply(GuardrailRules.INPUT_RULES, normalized, found)
        coupon = self._large_coupon(normalized)
        if coupon is not None:
            found[GuardrailReason.LARGE_COUPON_REQUEST] = coupon
        return self._result(found)

    def scan_document(self, document: ScannableDocument) -> GuardrailResult:
        """Flag documents that are untrusted or that give orders to the assistant."""
        found: dict[GuardrailReason, str] = {}
        if GuardrailRules.UNTRUSTED_AUDIENCE.search(document.audience or ""):
            found[GuardrailReason.UNTRUSTED_SOURCE] = self._clip(document.audience)
        unquoted = GuardrailRules.QUOTED_TEXT.sub(" ", self._normalize(document.text))
        self._apply(GuardrailRules.DOCUMENT_RULES, unquoted, found)
        return self._result(found)

    def filter_output(self, text: str | None, allowed_emails: Iterable[str] = ()) -> GuardrailResult:
        """Block drafts that disclose, over-promise, or claim unapproved actions.

        ``allowed_emails`` are addresses the draft may contain (the ticket's own
        customer). Any other address is treated as another customer's data.
        """
        normalized = self._normalize(text)
        found: dict[GuardrailReason, str] = {}

        for rule in GuardrailRules.OUTPUT_RULES:
            if rule.skip_if_hedged:
                self._apply_per_sentence(rule, normalized, found)
            else:
                self._apply((rule,), normalized, found)

        for secret in self._secrets:
            if secret in (text or ""):
                found.setdefault(GuardrailReason.SECRET_LEAK, "[configured secret]")

        folded = self._folded(normalized)
        if any(marker in folded for marker in self._prompt_markers):
            found.setdefault(GuardrailReason.PROMPT_LEAK, "[prompt text]")

        allowed = {e.strip().lower() for e in allowed_emails}
        for match in GuardrailRules.EMAIL.finditer(normalized):
            if match.group(0).lower() not in allowed:
                found.setdefault(GuardrailReason.OTHER_CUSTOMER_DATA, self._clip(match.group(0)))

        for match in GuardrailRules.CARD_NUMBER.finditer(normalized):
            digits = re.sub(r"\D", "", match.group(0))
            if self._luhn_valid(digits):
                found.setdefault(GuardrailReason.PAYMENT_DATA, f"[{len(digits)}-digit card number]")
        return self._result(found)

    # ---- internals --------------------------------------------------------

    def _apply(
        self,
        rules: Iterable[Rule],
        text: str,
        found: dict[GuardrailReason, str],
    ) -> None:
        for rule in rules:
            match = rule.pattern.search(text)
            if match:
                found.setdefault(rule.reason, self._clip(match.group(0)))

    def _apply_per_sentence(
        self, rule: Rule, text: str, found: dict[GuardrailReason, str]
    ) -> None:
        """Match a rule sentence by sentence, ignoring negated or conditional sentences."""
        for sentence in self._SENTENCE_SPLIT.split(text):
            match = rule.pattern.search(sentence)
            claim = GuardrailRules.COURTESY_OPENER.sub("", sentence)
            if match and not GuardrailRules.HEDGE.search(claim):
                found.setdefault(rule.reason, self._clip(match.group(0)))
                return

    def _large_coupon(self, text: str) -> str | None:
        for pattern in GuardrailRules.COUPON_AMOUNT:
            for match in pattern.finditer(text):
                amount = int(match.group(1).replace(",", "") or 0)
                if amount > self._max_coupon_inr:
                    return self._clip(match.group(0))
        return None

    def _result(self, found: dict[GuardrailReason, str]) -> GuardrailResult:
        return GuardrailResult(
            flagged=bool(found),
            reasons=tuple(found),
            evidence={reason.value: snippet for reason, snippet in found.items()},
        )

    def _clip(self, snippet: str) -> str:
        snippet = " ".join(snippet.split())
        if len(snippet) <= self._EVIDENCE_CHARS:
            return snippet
        return snippet[: self._EVIDENCE_CHARS - 3] + "..."

    @staticmethod
    def _normalize(text: str | None) -> str:
        """Fold look-alike characters and strip invisible ones so obfuscation fails."""
        if not text:
            return ""
        folded = unicodedata.normalize("NFKC", text)
        folded = GuardrailRules.ZERO_WIDTH.sub("", folded)
        return re.sub(r"[ \t\r\f\v]+", " ", folded)

    @staticmethod
    def _folded(text: str) -> str:
        return " ".join(text.split()).casefold()

    @staticmethod
    def _luhn_valid(digits: str) -> bool:
        if not 13 <= len(digits) <= 19:
            return False
        total = 0
        for index, char in enumerate(reversed(digits)):
            value = int(char)
            if index % 2 == 1:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
        return total % 10 == 0
