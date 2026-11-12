from typing import ClassVar


class MockDraftTemplates:
    """Reply text for the mock adapter, written from the knowledge-base policies.

    Only ``{item}`` is filled in, from the order record. Customer text is never
    copied into a reply, so a ticket cannot put words into the draft.
    """

    REFUND_DOC: ClassVar[str] = "KB-REFUND-001"
    SHIPPING_DOC: ClassVar[str] = "KB-SHIPPING-001"
    WARRANTY_DOC: ClassVar[str] = "KB-WARRANTY-001"
    BILLING_DOC: ClassVar[str] = "KB-BILLING-001"
    ACCOUNT_DOC: ClassVar[str] = "KB-ACCOUNT-001"
    SECURITY_DOC: ClassVar[str] = "KB-SECURITY-001"

    DEFAULT_ITEM: ClassVar[str] = "your item"

    GREETING: ClassVar[str] = "Hello {name},\n\n{body}"
    CANNOT_CONFIRM: ClassVar[str] = (
        "I cannot confirm an answer from our support policies, "
        "so a human specialist will review this."
    )

    DAMAGE_IN_WINDOW: ClassVar[str] = (
        "I am sorry that {item} arrived damaged. You reported this within the return window, so "
        "our policy allows either a replacement or a refund review. Please reply with a photo or "
        "a short description of the damage. A support specialist has to approve the next step "
        "before anything is processed."
    )
    DAMAGE_LATE: ClassVar[str] = (
        "I am sorry about the problem with {item}. The return window for this order has ended, "
        "so a human specialist needs to review which options apply. Please reply with a photo or "
        "a short description of the damage."
    )
    FINAL_SALE: ClassVar[str] = (
        "I understand you would like a refund for {item}. Software licenses and other marked "
        "items are final sale, so they are not eligible for a refund after purchase unless "
        "required by law or approved by a support manager. I am not able to approve a refund "
        "for this order."
    )
    REFUND_LATE: ClassVar[str] = (
        "I understand you would like to return {item}. The return window for this order has "
        "ended, so it is not eligible under the standard policy. I am not able to approve a "
        "refund. Any goodwill exception would need approval from a support specialist."
    )
    REFUND_IN_WINDOW: ClassVar[str] = (
        "Thanks for reaching out about {item}. Physical products may be returned within 7 "
        "calendar days of delivery when they are unused, defective, damaged on arrival, or "
        "materially different from the listing. A support specialist can start a refund review, "
        "and no money moves until that review is approved."
    )

    STALE_TRACKING: ClassVar[str] = (
        "I am sorry that the tracking for {item} has stopped moving. The next step is a carrier "
        "investigation. A replacement or refund review may be considered after carrier "
        "confirmation or after 10 business days without movement. I cannot promise an instant "
        "refund or an instant replacement because tracking is stale."
    )
    URGENT_NOTE: ClassVar[str] = (
        " Because you have a time-sensitive need, this ticket is marked high priority."
    )
    SHIPPING_STATUS: ClassVar[str] = (
        "Thanks for asking about the delivery of {item}. Most orders ship within 1 business day "
        "and arrive within 3 to 7 business days, depending on location and carrier capacity. If "
        "tracking shows no movement for 5 or more business days, we can open a carrier "
        "investigation."
    )

    SAFETY: ClassVar[str] = (
        "What you describe with {item} is a safety issue, so please stop using the device. I am "
        "escalating this to a human specialist with urgent priority, and the specialist will "
        "guide you on the next steps."
    )
    WARRANTY: ClassVar[str] = (
        "I am sorry about the problem with {item}. Electronics have a 12-month limited warranty "
        "from the delivery date, which covers manufacturing defects. A support specialist needs "
        "to review this and may ask for proof of purchase, the serial number and product photos. "
        "Any replacement under warranty requires human approval."
    )

    BILLING: ClassVar[str] = (
        "I am sorry about this billing concern. We will start a billing review to check the "
        "charges against your order. I cannot promise an immediate refund, and nothing is "
        "confirmed until payment operations has checked it. To help locate the payment, please "
        "share the transaction reference, or the payment date, amount, payment method type and "
        "the last four digits of the card."
    )

    ACCOUNT: ClassVar[str] = (
        "Account email changes and password resets require identity verification, and I cannot "
        "skip that check or change an account based only on a chat message. A human support "
        "specialist will help you complete verification."
    )
    SECRET_REFUSAL: ClassVar[str] = (
        "I cannot share system prompts, API keys, internal notes or other sensitive information. "
        "This request has been flagged and escalated to a human support specialist."
    )
    INJECTION_REFUSAL: ClassVar[str] = (
        "Your message included instructions aimed at changing how support works. I did not "
        "follow them. This unsafe instruction has been flagged and escalated to a human reviewer."
    )
    COUPON_REFUSAL: ClassVar[str] = " I cannot issue a coupon on this request."
