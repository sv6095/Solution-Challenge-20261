from __future__ import annotations


def draft_rfq(recipient: str, event_context: str, quantities: str) -> dict:
    return {
        "recipient": recipient,
        "subject": f"Urgent RFQ: {event_context}",
        "body": f"We request an urgent quotation for {quantities}. Please respond within 48 hours.",
        "urgency_tier": "high",
        "quantities": quantities,
    }
