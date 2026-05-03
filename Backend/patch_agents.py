import os
import re

AGENT_DIR = r"d:\Praecantator\Backend\agents"

agents = {
    "political_risk_agent.py": "Political",
    "tariff_risk_agent.py": "Tariff",
    "logistics_risk_agent.py": "Logistics"
}

inject_template = """
    if structured.findings:
        markdown_lines = [
            "## {title} Risk Analysis",
            "| Category | Geography | Severity | Likelihood | Impact | Actions |",
            "|---|---|---|---|---|---|",
        ]
        for f in findings:
            acts = "<br>".join(f"**{a.owner}**: {a.action}" for a in f.recommended_actions)
            impact = f.operational_impact.replace("|", "/")
            markdown_lines.append(f"| {f.category} | {f.geography} | {f.severity} | {f.likelihood:.2f} | {impact} | {acts} |")

    packet = AgentPacket("""

for filename, title in agents.items():
    path = os.path.join(AGENT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Replace "packet = AgentPacket("
    # Only the first literal "    packet = AgentPacket(" at the top level
    
    # Find "    packet = AgentPacket("
    content = content.replace("    packet = AgentPacket(", inject_template.format(title=title), 1)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Patched {filename}")

