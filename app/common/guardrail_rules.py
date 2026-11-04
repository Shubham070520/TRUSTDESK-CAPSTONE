"""Pattern definitions for the guardrail scanner. Data only, no behavior.

Three rule sets, one per place text is checked:

* ``INPUT_RULES``    customer messages (untrusted input)
* ``DOCUMENT_RULES`` retrieved documents (untrusted context)
* ``OUTPUT_RULES``   model drafts before they are stored or shown

Output rules look for *disclosure and commitments*, not for mentions. A
refusal such as "I can't share internal notes" must pass.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class GuardrailReason(str, Enum):
    # --- input ---
    IGNORE_INSTRUCTIONS = "ignore_instructions"
    SYSTEM_OVERRIDE = "system_override"
    REVEAL_SYSTEM_PROMPT = "reveal_system_prompt"
    SECRET_REQUEST = "secret_request"
    INTERNAL_NOTES_REQUEST = "internal_notes_request"
    HIDE_FROM_REVIEWER = "hide_from_reviewer"
    SKIP_VERIFICATION = "skip_verification"
    LARGE_COUPON_REQUEST = "large_coupon_request"
    # --- documents ---
    UNTRUSTED_SOURCE = "untrusted_source"
    ADDRESSES_ASSISTANT = "addresses_assistant"
    OVERRIDE_DIRECTIVE = "override_directive"
    CONCEALMENT_DIRECTIVE = "concealment_directive"
    BLANKET_APPROVAL = "blanket_approval"
    REVEAL_DIRECTIVE = "reveal_directive"
    # --- output ---
    SECRET_LEAK = "secret_leak"
    PROMPT_LEAK = "prompt_leak"
    INTERNAL_NOTES_LEAK = "internal_notes_leak"
    OTHER_CUSTOMER_DATA = "other_customer_data"
    PAYMENT_DATA = "payment_data"
    PAYMENT_DETAILS_REQUEST = "payment_details_request"
    PROMISED_OUTCOME = "promised_outcome"
    CLAIMED_ACTION = "claimed_action"
    INJECTED_INSTRUCTION = "injected_instruction"


@dataclass(frozen=True)
class Rule:
    """One pattern. ``skip_if_hedged`` ignores sentences that negate or condition the claim."""

    reason: GuardrailReason
    pattern: re.Pattern[str]
    skip_if_hedged: bool = False

    @classmethod
    def of(cls, reason: GuardrailReason, regex: str, skip_if_hedged: bool = False) -> "Rule":
        return cls(reason, re.compile(regex, re.IGNORECASE), skip_if_hedged)


class GuardrailRules:
    # Verbs that ask for something to be shown or handed over.
    _ASK = (
        r"(?:reveal|show|print|display|output|repeat|share|leak|dump|expose|give|tell|send|"
        r"provide|list|read|disclose)"
    )
    # Where the customer talks to the system as if it were an operator.
    _TO_HUMAN = r"(?:human|reviewer|supervisor|manager|agent|team|anyone|audit|logs?)"

    INPUT_RULES: ClassVar[tuple[Rule, ...]] = (
        Rule.of(
            GuardrailReason.IGNORE_INSTRUCTIONS,
            r"\b(?:ignore|disregard|forget|override)\b\s+(?:\w+\s+){0,3}?"
            r"(?:instructions?|rules?|polic(?:y|ies)|guidelines?|guardrails?|restrictions?|prompts?)\b"
            r"|\b(?:ignore|disregard)\s+(?:all\s+of\s+|all\s+)?(?:the\s+)?(?:above|previous|prior|earlier)\b"
            r"|\b(?:ignore|disregard|forget)\s+(?:everything|anything|all)\b[^.\n]{0,30}"
            r"\b(?:above|before|told|said|earlier|previously|given)\b",
        ),
        Rule.of(
            GuardrailReason.SYSTEM_OVERRIDE,
            r"\bsystem\s+override\b"
            r"|\byou\s+are\s+now\s+(?:allowed|able|permitted|authori[sz]ed|free|in)\b"
            r"|\bnew\s+instructions?\s*:"
            r"|\bdeveloper\s+mode\b|\bjailbreak\b"
            r"|\bpretend\s+(?:to\s+be|you\s+are)\b"
            r"|\b(?:policy|policies|rules?)\s+(?:has|have)\s+(?:just\s+)?changed\b"
            r"|\bact\s+as\s+(?:if\b|an?\s+(?:admin|manager|developer))"
            r"|\bnew\s+policy\s*:"
            r"|\bcorrect\s+support\s+behaviou?r\s+is\b"
            r"|\bapprove\s+(?:every|all|any)\s+(?:refunds?|requests?)\b"
            r"|\bissue\s+a\s+coupon\s+whenever\b"
            r"|\bwhenever\s+the\s+customer\s+asks\b",
        ),
        Rule.of(
            GuardrailReason.REVEAL_SYSTEM_PROMPT,
            r"\b(?:system|hidden|secret)\s+(?:prompts?|instructions?|messages?)\b"
            r"|\binternal\s+instructions?\b"
            rf"|\b{_ASK}\b[^.\n]{{0,30}}\byour\s+(?:prompts?|instructions|rules|guidelines)\b"
            rf"|\b{_ASK}\b[^.\n]{{0,30}}\b(?:text|words|message|prompt|instructions)\s+above\b"
            r"|\b(?:the\s+)?prompt\s+you\s+(?:were|are)\s+given\b",
        ),
        Rule.of(
            GuardrailReason.SECRET_REQUEST,
            rf"\b{_ASK}\b[^.\n]{{0,60}}\b(?:api[\s_-]?keys?|secret[\s_-]?keys?|private[\s_-]?keys?|"
            r"(?:access|auth(?:entication)?|bearer|session)[\s_-]?tokens?|secrets?)\b",
        ),
        Rule.of(
            GuardrailReason.INTERNAL_NOTES_REQUEST,
            rf"\b{_ASK}\b[^.\n]{{0,80}}\binternal[\s-]+(?:notes?|documents?|docs?|memos?|policies)\b",
        ),
        Rule.of(
            GuardrailReason.HIDE_FROM_REVIEWER,
            rf"\b(?:do\s+not|don'?t|dont|never|without)\s+(?:\w+\s+){{0,2}}?"
            rf"(?:mention|tell|inform|notify|show|disclose|log|record|report|alert)\b[^.\n]{{0,50}}\b{_TO_HUMAN}\b"
            rf"|\b(?:hide|conceal)\b[^.\n]{{0,40}}\b(?:from|away\s+from)\b[^.\n]{{0,25}}\b{_TO_HUMAN}\b"
            r"|\b(?:do\s+not|don'?t|never)\s+mention\b[^.\n]{0,40}\b(?:document|note)\b"
            r"|\bkeep\b[^.\n]{0,30}\b(?:secret|hidden|between\s+us)\b"
            r"|\bsecretly\b",
        ),
        Rule.of(
            GuardrailReason.SKIP_VERIFICATION,
            r"\b(?:ignore|skip|bypass|waive|disable|without|no\s+need\s+for)\b\s+(?:\w+\s+){0,2}?"
            r"(?:identity|verification|verifying|kyc|authentication|2fa|two[\s-]factor|otp|security)"
            r"(?:\s+(?:checks?|verification|steps?|process|questions?))?",
        ),
    )

    # Documents may legitimately *quote* attack phrases as examples (KB-SECURITY-001).
    # Quoted text is removed before these rules run, so only direct instructions match.
    DOCUMENT_RULES: ClassVar[tuple[Rule, ...]] = (
        Rule.of(
            GuardrailReason.ADDRESSES_ASSISTANT,
            r"\b(?:attention|attn|note\s+to|dear|hey)\b[^.\n]{0,30}\b(?:assistant|ai|agent|bot|model)\b",
        ),
        Rule.of(
            GuardrailReason.OVERRIDE_DIRECTIVE,
            r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?"
            r"(?:previous|prior|above|earlier|existing)\s+"
            r"(?:policies|policy|instructions|rules|guidelines|guardrails)\b",
        ),
        Rule.of(
            GuardrailReason.CONCEALMENT_DIRECTIVE,
            r"\b(?:do\s+not|don'?t|never)\s+(?:mention|tell|disclose|reveal)\b[^.\n]{0,40}"
            r"\b(?:document|note|reviewer|human|supervisor)\b",
        ),
        Rule.of(
            GuardrailReason.BLANKET_APPROVAL,
            r"\b(?:approve|issue|grant|accept)\s+(?:every|all|any)\b"
            r"|\b(?:issue|give|grant)\s+a\s+(?:coupon|refund)\s+whenever\b"
            r"|\bwhenever\s+the\s+customer\s+asks\b",
        ),
        Rule.of(
            GuardrailReason.REVEAL_DIRECTIVE,
            r"\breveal\s+(?:all\s+|any\s+|your\s+)?(?:hidden|internal|system|secret)\b",
        ),
    )

    # Audiences that mark a document as coming from outside the company.
    UNTRUSTED_AUDIENCE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:imported|vendor|third[\s-]party|external|unverified)\b", re.IGNORECASE
    )

    OUTPUT_RULES: ClassVar[tuple[Rule, ...]] = (
        Rule.of(
            GuardrailReason.PROMISED_OUTCOME,
            r"\b(?:instant|immediate|immediately|instantly)\b[^.\n]{0,25}\b(?:refunds?|replacements?|credits?)\b"
            r"|\b(?:refunds?|replacements?|credits?)\b[^.\n]{0,30}\b(?:instantly|immediately|right\s+away)\b"
            r"|\b(?:we|i)(?:'ve|’ve|\s+have)\s+(?:already\s+)?(?:refunded|"
            r"(?:processed|issued|approved)\s+(?:a|your|the)\s+refund)"
            r"|\byour\s+refund\s+(?:has\s+been|is|was)\s+(?:processed|issued|completed|approved|sent)\b"
            r"|\byour\s+replacement\s+(?:has\s+been|is|was)\s+(?:created|shipped|dispatched|ordered|placed)\b"
            r"|\b(?:guarantee[sd]?|promise[sd]?)\b[^.\n]{0,20}\b(?:refund|replacement)\b"
            r"|\bapprove[sd]?\s+(?:every|all|any)\s+(?:refunds?|requests?)\b"
            r"|\byou(?:'ll|’ll|\s+will)\s+(?:get|receive)\b[^.\n]{0,25}\b(?:coupons?|vouchers?|refunds?|replacements?)\b"
            r"|\byour\s+(?:refund|replacement)\s+will\s+(?:arrive|reach|ship|be\s+(?:credited|processed|issued|sent|shipped))\b",
            skip_if_hedged=True,
        ),
        Rule.of(
            GuardrailReason.CLAIMED_ACTION,
            r"\b(?:we|i)(?:'ve|’ve|\s+have)\s+(?:already\s+)?(?:issued|created|sent|applied|added)\b"
            r"[^.\n]{0,25}\b(?:coupons?|vouchers?|promo|discount)\b"
            r"|\b(?:we|i)(?:'ve|’ve|\s+have)\s+(?:already\s+)?(?:changed|updated|reset|locked|deleted)\b"
            r"[^.\n]{0,25}\b(?:email|password|account)\b"
            r"|\byour\s+(?:account\s+)?(?:email|password|account)\s+(?:has\s+been|was|is\s+now)\s+"
            r"(?:changed|updated|reset|locked|deleted)\b"
            r"|\b(?:we|i)(?:'ll|’ll|\s+will|\s+am\s+going\s+to|\s+can)\s+(?:issue|send|give|apply|add|create)\b"
            r"[^.\n]{0,25}\b(?:coupons?|vouchers?|promo|discount)\b"
            r"|\bhere(?:'s|’s|\s+is)\s+(?:your|a)\b[^.\n]{0,20}\b(?:coupon|voucher)\b"
            r"|\b(?:coupon|voucher|promo)\s+code\b"
            r"|\b(?:coupons?|vouchers?)\b[^.\n]{0,20}\b(?:has|have)\s+been\s+(?:issued|created|sent|applied|added)\b"
            r"|\b(?:we|i)(?:'ll|’ll|\s+will|\s+am\s+going\s+to)\s+(?:change|update|reset|lock|delete)\b"
            r"[^.\n]{0,25}\b(?:email|password|account)\b"
            r"|\b(?:we|i)(?:'ve|’ve|'ll|’ll|\s+have|\s+will)\s+(?:skipped|skip|waived|waive|bypassed|bypass)\b"
            r"[^.\n]{0,25}\b(?:verification|identity|checks?)\b",
            skip_if_hedged=True,
        ),
        Rule.of(
            GuardrailReason.PAYMENT_DETAILS_REQUEST,
            r"\b(?:send|share|provide|give|tell|enter|type|confirm|reply\s+with)\b[^.\n]{0,40}"
            r"\b(?:cvv|cvc|otp|one[\s-]time\s+(?:password|code)|pin|full\s+card\s+number|"
            r"(?:net[\s-]?)?banking\s+password)\b",
            skip_if_hedged=True,
        ),
        Rule.of(
            GuardrailReason.SECRET_LEAK,
            r"\bsk-[A-Za-z0-9_\-]{16,}"
            r"|\bAIza[0-9A-Za-z_\-]{20,}"
            r"|\bgsk_[A-Za-z0-9]{16,}"
            r"|\bBearer\s+[A-Za-z0-9._\-]{16,}"
            r"|\bapi[\s_-]?key\s*[:=]\s*\S+"
            r"|\bapi[\s_-]?key\s+is\s+(?!not\b)\S+",
        ),
        Rule.of(
            GuardrailReason.PROMPT_LEAK,
            r"\b(?:here\s+(?:is|are)|these\s+are|below\s+(?:is|are))\b[^.\n]{0,30}"
            r"\b(?:system|hidden|secret|internal)\s+(?:prompts?|instructions?)\b"
            r"|\b(?:system|hidden)\s+prompt\s*[:=]"
            r"|\byou\s+are\s+(?:a|an|the)\s+(?:helpful\s+|customer\s+)?(?:support|trustdesk)\s+(?:assistant|agent|bot)\b"
            r"|\b(?:my|the)\s+(?:system\s+prompt|hidden\s+prompt|(?:hidden\s+|secret\s+|internal\s+)?instructions)\s+"
            r"(?:is|are|says?|states?)\b"
            r"|</?(?:ticket_data|triage_data|policy_documents)>",
        ),
        Rule.of(
            GuardrailReason.INTERNAL_NOTES_LEAK,
            r"\binternal[\s-]+notes?\s*[:=]"
            r"|\bhere\s+(?:is|are)\b[^.\n]{0,20}\binternal[\s-]+notes?\b"
            r"|\binternal[\s-]+notes?\b[^.\n]{0,15}\b(?:says?|states?|shows?|indicates?|mentions?|reads?)\b",
        ),
        # Words that only make sense as an attack, repeated by a model that fell for one.
        Rule.of(
            GuardrailReason.INJECTED_INSTRUCTION,
            r"\b(?:attention|attn)\b[^.\n]{0,30}\b(?:assistant|ai|agent|bot|model)\b\s*:"
            r"|\b(?:do\s+not|don'?t|never)\s+(?:mention|tell|disclose)\b[^.\n]{0,40}"
            r"\b(?:document|reviewer|human|supervisor)\b",
        ),
        Rule.of(
            GuardrailReason.INJECTED_INSTRUCTION,
            r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:policies|instructions|rules)\b"
            r"|\breveal\s+all\s+hidden\s+instructions\b"
            r"|\bcorrect\s+support\s+behaviou?r\s+is\b",
            skip_if_hedged=True,
        ),
    )

    # Sentences that negate or condition a claim ("we cannot promise an instant refund").
    HEDGE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:not|cannot|unable|never|no|without|nor|unless|until|once|if|after|pending|"
        r"subject\s+to|depending|may|might|could|would|whether)\b|n['’]t\b|\bcan\s+not\b",
        re.IGNORECASE,
    )

    # Friendly openers that contain a hedge word but do not hedge what follows.
    COURTESY_OPENER: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*(?:no\s+(?:problem|worries)|not\s+a\s+problem|if\s+you\s+(?:like|want|wish|prefer)|"
        r"if\s+you'd\s+like)\b[,.!:\s-]*",
        re.IGNORECASE,
    )

    # A request for a coupon above the standard limit, e.g. "5000 INR coupon" or "coupon of 5000".
    COUPON_AMOUNT: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(
            r"\b(\d[\d,]*)\s*(?:inr|rs\.?|rupees?|₹)?\s*(?:\w+\s+){0,2}?(?:coupons?|vouchers?|discount|credit)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:coupons?|vouchers?)\s+(?:of|worth|for)\s*(?:inr|rs\.?|₹)?\s*(\d[\d,]*)",
            re.IGNORECASE,
        ),
    )

    EMAIL: ClassVar[re.Pattern[str]] = re.compile(
        r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    )
    CARD_NUMBER: ClassVar[re.Pattern[str]] = re.compile(
        r"(?<![A-Za-z0-9])(?:\d[ -]?){13,19}(?![A-Za-z0-9])"
    )
    QUOTED_TEXT: ClassVar[re.Pattern[str]] = re.compile(r'"[^"\n]{0,200}"|“[^”\n]{0,200}”')
    ZERO_WIDTH: ClassVar[re.Pattern[str]] = re.compile("[​-\u200F⁠﻿­]")
