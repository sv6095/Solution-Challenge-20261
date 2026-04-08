from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
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


def _draw_wrapped(pdf: canvas.Canvas, x: int, y: int, text: str, max_width: int, line_height: int = 14) -> int:
    """
    Draw simple wrapped text (monospace-free) using stringWidth.
    Returns updated y after drawing.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = (text or "").split()
    if not words:
        return y
    line: list[str] = []
    while words:
        line.append(words.pop(0))
        w = stringWidth(" ".join(line), pdf._fontname, pdf._fontsize)  # type: ignore[attr-defined]
        if w > max_width and len(line) > 1:
            # draw previous line
            last = line.pop()
            pdf.drawString(x, y, " ".join(line))
            y -= line_height
            line = [last]
    if line:
        pdf.drawString(x, y, " ".join(line))
        y -= line_height
    return y


def generate_workflow_audit_report_pdf(report: dict, requested_by: str = "system") -> bytes:
    """
    Generates a detailed multi-section audit report PDF from a stored workflow report dict.
    """
    def _get(d: dict, *keys: str, default: str = "—") -> str:
        cur: object = d
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        if cur is None or cur == "":
            return default
        return str(cur)

    def _route_rows(route_comparison: list[dict]) -> list[list[str]]:
        rows: list[list[str]] = []
        for r in (route_comparison or [])[:3]:
            mode = str(r.get("mode") or "—")
            lane = str(r.get("lane") or "—") if mode == "sea" else "—"
            # time
            if mode == "air":
                time = f"{r.get('flight_hours', '—')} hrs"
            elif mode == "sea":
                time = f"{r.get('transit_days', '—')} days"
            else:
                # land: prefer maps duration if present
                maps = r.get("maps") if isinstance(r.get("maps"), dict) else {}
                sssp = r.get("sssp") if isinstance(r.get("sssp"), dict) else {}
                time = f"maps {maps.get('duration_hours', '—')} hrs / sssp {sssp.get('duration_hours', '—')} hrs"
            # cost
            cost_usd = r.get("cost_usd")
            if cost_usd is None and isinstance(r.get("maps"), dict):
                cost_usd = (r.get("maps") or {}).get("cost_usd")
            if cost_usd is None and isinstance(r.get("sssp"), dict):
                cost_usd = (r.get("sssp") or {}).get("cost_usd")
            cost = f"${float(cost_usd):,.0f}" if isinstance(cost_usd, (int, float)) else "—"
            rows.append([mode.upper(), lane, time, cost])
        return rows

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.70 * inch,
        bottomMargin=0.70 * inch,
        title=f"Praecantator Workflow Audit {report.get('workflow_id', '')}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=10,
    )
    h_style = ParagraphStyle(
        "h",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#111827"),
    )
    label_style = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )
    value_style = ParagraphStyle(
        "value",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#374151"),
    )
    small_style = ParagraphStyle(
        "small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4B5563"),
    )

    def header_footer(c: canvas.Canvas, d) -> None:  # type: ignore[no-untyped-def]
        c.saveState()
        c.setFillColor(colors.HexColor("#111827"))
        c.setFont("Helvetica", 8.5)
        c.drawString(doc.leftMargin, 18, f"Workflow: {report.get('workflow_id', 'unknown')}")
        c.drawRightString(A4[0] - doc.rightMargin, 18, f"Page {c.getPageNumber()}")
        c.restoreState()

    story: list = []
    story.append(Paragraph("Praecantator — Workflow Audit Report", title_style))
    story.append(Paragraph(f"<b>Workflow ID:</b> {_get(report, 'workflow_id')}", value_style))
    story.append(Paragraph(f"<b>Generated at:</b> {datetime.now(timezone.utc).isoformat()}", value_style))
    story.append(Paragraph(f"<b>Requested by:</b> {requested_by}", value_style))
    story.append(Spacer(1, 10))

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    summary_rows = [
        ["Dominant signal", str(summary.get("event_title") or "—")],
        ["Region", str(summary.get("region") or "—")],
        ["Affected nodes", str(summary.get("affected_nodes") or 0)],
        ["Estimated exposure (USD)", str(summary.get("exposure_usd") or "—")],
        ["Recommended mode", str(summary.get("recommended_mode") or "—")],
        ["Action executed", str(summary.get("action_taken") or "—")],
        ["Total response time", f"{summary.get('response_time_seconds') or '—'} seconds"],
    ]
    story.append(Paragraph("Executive Summary", h_style))
    t = Table(summary_rows, colWidths=[140, 360])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)

    # Stage 1 — Detect
    detect = report.get("detect") if isinstance(report.get("detect"), dict) else {}
    evt = detect.get("event") if isinstance(detect.get("event"), dict) else {}
    incident_stream = detect.get("incident_stream") if isinstance(detect.get("incident_stream"), list) else []
    story.append(Paragraph("Stage 1 — DETECT (Signal Intake)", h_style))
    story.append(
        Table(
            [
                [Paragraph("Event", label_style), Paragraph(str(evt.get("title") or evt.get("event_type") or "—"), value_style)],
                [Paragraph("Severity", label_style), Paragraph(str(evt.get("severity") or "—"), value_style)],
                [Paragraph("Location/Region", label_style), Paragraph(str(evt.get("region") or evt.get("location") or "—"), value_style)],
                [Paragraph("Timestamp", label_style), Paragraph(str(evt.get("timestamp") or detect.get("detected_at") or "—"), value_style)],
                [
                    Paragraph("Incident stream (sample)", label_style),
                    Paragraph(
                        "<br/>".join([str(i.get("title") or "—") for i in incident_stream[:3]]) or "—",
                        small_style,
                    ),
                ],
            ],
            colWidths=[140, 360],
        )
    )

    # Stage 2 — Assess
    assess = report.get("assess") if isinstance(report.get("assess"), dict) else {}
    analysis_text = str(assess.get("analysis") or "").strip()
    story.append(Paragraph("Stage 2 — ASSESS (Impact Analysis)", h_style))
    assess_table = Table(
        [
            [Paragraph("Analysis engine", label_style), Paragraph(str(assess.get("analysis_provider") or "local"), value_style)],
            [Paragraph("Confidence", label_style), Paragraph(str(assess.get("confidence") or "—"), value_style)],
            [Paragraph("Days at risk", label_style), Paragraph(str(assess.get("days_at_risk") or "—"), value_style)],
            [Paragraph("Exposure (USD)", label_style), Paragraph(str(assess.get("exposure_usd") or "—"), value_style)],
        ],
        colWidths=[140, 360],
    )
    assess_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(assess_table)
    if analysis_text:
        # Clean markdown-ish "###" headers to bold headings
        cleaned = []
        for line in analysis_text.splitlines():
            l = line.strip()
            if l.startswith("###"):
                cleaned.append(f"<b>{l.replace('###', '').strip()}</b>")
            elif l.startswith("- "):
                cleaned.append(f"• {l[2:].strip()}")
            else:
                cleaned.append(l)
        story.append(Spacer(1, 8))
        story.append(Paragraph("Brief analysis", ParagraphStyle("bh", parent=h_style, fontSize=11)))
        story.append(Paragraph("<br/>".join([c for c in cleaned if c]), value_style))

    # Stage 3 — Decide
    decide = report.get("decide") if isinstance(report.get("decide"), dict) else {}
    story.append(Paragraph("Stage 3 — DECIDE (Routing + Recommendation)", h_style))
    story.append(
        Table(
            [
                [Paragraph("Recommended mode", label_style), Paragraph(str(decide.get("recommended_mode") or "—"), value_style)],
                [Paragraph("Currency risk index", label_style), Paragraph(str(decide.get("currency_risk_index") or "—"), value_style)],
            ],
            colWidths=[140, 360],
        )
    )
    rc = decide.get("route_comparison") if isinstance(decide.get("route_comparison"), list) else []
    rc_rows = _route_rows([r for r in rc if isinstance(r, dict)])
    if rc_rows:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Mode comparison (top 3)", ParagraphStyle("bh2", parent=h_style, fontSize=11)))
        rt = Table([["MODE", "LANE", "TIME", "COST (USD)"], *rc_rows], colWidths=[70, 90, 250, 90])
        rt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(rt)

    # Stage 4 — Act
    act = report.get("act") if isinstance(report.get("act"), dict) else {}
    story.append(Paragraph("Stage 4 — ACT (Execution)", h_style))
    act_table = Table(
        [
            [Paragraph("Decision selected", label_style), Paragraph(str(act.get("decision") or "—"), value_style)],
            [Paragraph("Executed at", label_style), Paragraph(str(act.get("executed_at") or "—"), value_style)],
            [Paragraph("Execution details", label_style), Paragraph(str(act.get("details") or "—"), value_style)],
        ],
        colWidths=[140, 360],
    )
    act_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB"))]))
    story.append(act_table)

    # Stage 5 — Audit
    audit = report.get("audit") if isinstance(report.get("audit"), dict) else {}
    story.append(Paragraph("Stage 5 — AUDIT (Compliance)", h_style))
    audit_table = Table(
        [
            [Paragraph("Audit status", label_style), Paragraph(str(audit.get("status") or "complete"), value_style)],
            [Paragraph("Workflow timeline", label_style), Paragraph(str(audit.get("timeline") or "—"), value_style)],
            [Paragraph("Response time", label_style), Paragraph(f"{audit.get('response_time_seconds') or '—'} seconds", value_style)],
        ],
        colWidths=[140, 360],
    )
    audit_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB"))]))
    story.append(audit_table)

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buffer.getvalue()
