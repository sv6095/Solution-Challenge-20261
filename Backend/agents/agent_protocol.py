from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EvidenceItem:
    source_name: str
    source_url: str
    title: str
    verified: bool = False
    citation_type: str = "derived"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendedAction:
    priority: str
    owner: str
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskFinding:
    category: str
    geography: str
    severity: str
    likelihood: float
    operational_impact: str
    financial_impact_hint: str
    time_horizon: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    recommended_actions: list[RecommendedAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "geography": self.geography,
            "severity": self.severity,
            "likelihood": self.likelihood,
            "operational_impact": self.operational_impact,
            "financial_impact_hint": self.financial_impact_hint,
            "time_horizon": self.time_horizon,
            "evidence": [item.to_dict() for item in self.evidence],
            "recommended_actions": [item.to_dict() for item in self.recommended_actions],
        }


@dataclass
class AgentPacket:
    agent: str
    confidence: float
    summary: str
    findings: list[RiskFinding] = field(default_factory=list)
    key_metrics: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""
    escalation_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "confidence": self.confidence,
            "summary": self.summary,
            "findings": [item.to_dict() for item in self.findings],
            "key_metrics": self.key_metrics,
            "markdown": self.markdown,
            "escalation_required": self.escalation_required,
        }


@dataclass
class SupervisorPacket:
    mission: str
    selected_agents: list[str]
    priority_order: list[str]
    decision_brief: str
    global_confidence: float
    recommended_path: str
    human_gate_required: bool
    rationale: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
