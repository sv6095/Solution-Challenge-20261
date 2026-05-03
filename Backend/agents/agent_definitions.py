from __future__ import annotations

SCHEDULER_AGENT = "scheduler_agent"
REPORTING_AGENT = "reporting_agent"
ASSISTANT_AGENT = "assistant_agent"
POLITICAL_RISK_AGENT = "political_risk_agent"
TARIFF_RISK_AGENT = "tariff_risk_agent"
LOGISTICS_RISK_AGENT = "logistics_risk_agent"


def get_scheduler_agent_instructions() -> str:
    return (
        "Analyze schedule and delivery context, compute timing risk, summarize equipment and lane exposure, "
        "and return structured data other agents can use."
    )


def get_political_risk_agent_instructions() -> str:
    return (
        "Analyze country-level policy, sanctions, governance, and unrest risks affecting manufacturing and "
        "cross-border delivery plans. Produce concrete risks and mitigations."
    )


def get_tariff_risk_agent_instructions() -> str:
    return (
        "Analyze tariff, customs, trade-policy, and duty-related risks affecting the shipment plan. "
        "Produce concrete risks and mitigations."
    )


def get_logistics_risk_agent_instructions() -> str:
    return (
        "Analyze routing, port, airport, congestion, weather, strike, and lane disruption risks. "
        "Produce concrete risks and mitigations."
    )


def get_reporting_agent_instructions() -> str:
    return (
        "Consolidate schedule, political, tariff, and logistics outputs into one executive report with "
        "prioritized actions and a clear risk summary."
    )


def get_assistant_agent_instructions() -> str:
    return (
        "Answer general supply-chain workflow questions, explain available analyses, and guide the user "
        "toward specific schedule or risk workflows."
    )
