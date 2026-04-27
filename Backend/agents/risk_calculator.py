from __future__ import annotations


def calculate_risk_percentage(days_variance: int, days_until_due: int) -> float:
    """Ported from Riskwise RiskCalculationPlugin.calculate_risk_percentage."""
    if days_until_due <= 0:
        return 100.0
    return abs(days_variance / days_until_due * 100)


def categorize_risk(risk_percentage: float) -> dict[str, str | int]:
    """Ported from Riskwise RiskCalculationPlugin.categorize_risk."""
    if risk_percentage < 5:
        return {"risk_flag": "Low Risk", "risk_points": 1, "color": "#10d98a"}
    if risk_percentage < 15:
        return {"risk_flag": "Medium Risk", "risk_points": 3, "color": "#f59e0b"}
    return {"risk_flag": "High Risk", "risk_points": 5, "color": "#ef4444"}
