from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate_audit_certificate(audit_id: str, user_id: str, summary_lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Praecantator Audit {audit_id}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, 800, "Praecantator Compliance Audit Certificate")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 776, f"Audit ID: {audit_id}")
    pdf.drawString(72, 760, f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    pdf.drawString(72, 744, f"Requested by: {user_id}")
    y = 710
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Workflow Summary")
    y -= 20
    pdf.setFont("Helvetica", 10)
    for line in summary_lines[:20]:
        pdf.drawString(84, y, f"- {line}")
        y -= 14
        if y < 72:
            pdf.showPage()
            y = 800
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
