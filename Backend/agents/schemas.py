from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCallModel(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)


class ToolPlanModel(BaseModel):
    rationale: str = ""
    tool_calls: list[ToolCallModel] = Field(default_factory=list, max_length=4)


class EvidenceModel(BaseModel):
    source_name: str
    source_url: str = ""
    title: str
    verified: bool = False
    citation_type: str = "derived"


class ActionModel(BaseModel):
    priority: str
    owner: str
    action: str
    reason: str


class RiskFindingModel(BaseModel):
    category: str
    geography: str
    severity: str
    likelihood: float = Field(ge=0.0, le=1.0)
    operational_impact: str
    financial_impact_hint: str
    time_horizon: str
    evidence: list[EvidenceModel] = Field(default_factory=list)
    recommended_actions: list[ActionModel] = Field(default_factory=list)


class SpecialistOutputModel(BaseModel):
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    escalation_required: bool = False
    key_metrics: dict = Field(default_factory=dict)
    findings: list[RiskFindingModel] = Field(default_factory=list)


class SupervisorOutputModel(BaseModel):
    mission: str
    selected_agents: list[str]
    priority_order: list[str]
    decision_brief: str
    global_confidence: float = Field(ge=0.0, le=1.0)
    recommended_path: str
    human_gate_required: bool
    rationale: list[str] = Field(default_factory=list)
