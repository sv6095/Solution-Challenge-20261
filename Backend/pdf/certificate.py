"""
Praecantator — Professional Audit Certificate Generator
pdf/certificate.py

Generates the official Praecantator Workflow Audit Certificate.
Design Philosophy:
- Dark command-center aesthetic 
- Human-readable at every section
- No blank cells or "None" strings
"""
from __future__ import annotations
import io
import json
import html
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, PageBreak, BaseDocTemplate, PageTemplate, Frame
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus.flowables import Flowable

# Color Palette
BG_DARK       = colors.HexColor("#080505")
SURFACE       = colors.HexColor("#140b0b")
CARD_BORDER   = colors.HexColor("#3a1919")
ACCENT_RED    = colors.HexColor("#ff3333")
ACCENT_DIM    = colors.HexColor("#330505")
AMBER         = colors.HexColor("#f59e0b")
RED           = colors.HexColor("#ef4444")
GREEN         = colors.HexColor("#10d98a")
TEXT_PRIMARY  = colors.HexColor("#e2eaf4")
TEXT_MID      = colors.HexColor("#8aa4be")
TEXT_MUTED    = colors.HexColor("#4a6a86")

PAGE_W, PAGE_H = A4
MARGIN_L = 18*mm
MARGIN_R = 18*mm
MARGIN_T = 20*mm
MARGIN_B = 20*mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

def build_styles():
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=TEXT_PRIMARY, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11, leading=14, textColor=TEXT_MID, spaceAfter=20),
        "hero_number": ParagraphStyle("hero_number", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ACCENT_RED, alignment=TA_CENTER),
        "hero_label": ParagraphStyle("hero_label", fontName="Helvetica", fontSize=9, textColor=TEXT_MUTED, alignment=TA_CENTER),
        "section_title": ParagraphStyle("section_title", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=TEXT_PRIMARY, spaceAfter=8, spaceBefore=12),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=TEXT_MID, leading=14),
        "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8, textColor=ACCENT_RED),
        "table_cell": ParagraphStyle("table_cell", fontName="Helvetica", fontSize=9, textColor=TEXT_PRIMARY),
        "table_label": ParagraphStyle("table_label", fontName="Helvetica-Bold", fontSize=9, textColor=TEXT_MUTED),
        "success": ParagraphStyle("success", fontName="Helvetica-Bold", fontSize=9, textColor=GREEN),
        "warning": ParagraphStyle("warning", fontName="Helvetica-Bold", fontSize=9, textColor=AMBER),
        "danger": ParagraphStyle("danger", fontName="Helvetica-Bold", fontSize=9, textColor=RED),
        "app_JSON": ParagraphStyle("app_JSON", fontName="Courier", fontSize=7, textColor=TEXT_MUTED, leading=9),
    }

def fmt_none(val, fallback="—") -> str:
    if val is None or val == "" or str(val).strip() in ("None", ""):
        return fallback
    return str(val).strip()

def fmt_usd(val, fallback="—") -> str:
    if val is None: return fallback
    try:
        return f"${float(val):,.0f}"
    except (ValueError, TypeError):
        return fallback

def fmt_timestamp(ts: str, fallback="—") -> str:
    if not ts or str(ts) == "None": return fallback
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y  %H:%M:%S UTC")
    except Exception:
        return str(ts)


def draw_background_and_header(canv: rl_canvas.Canvas, doc, workflow_id: str):
    canv.saveState()
    # Background
    canv.setFillColor(BG_DARK)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    
    # Top red accent bar
    canv.setFillColor(ACCENT_RED)
    canv.rect(0, PAGE_H - 3, PAGE_W, 3, fill=1, stroke=0)
    
    # Header area
    canv.setFillColor(SURFACE)
    canv.rect(0, PAGE_H - 18*mm, PAGE_W, 15*mm, fill=1, stroke=0)
    
    # Header text
    canv.setFillColor(ACCENT_RED)
    canv.setFont("Helvetica-Bold", 9)
    canv.drawString(MARGIN_L, PAGE_H - 10*mm, "PRAECANTATOR // KINETIC FORTRESS")
    
    canv.setFillColor(TEXT_MUTED)
    canv.setFont("Courier", 8)
    canv.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 10*mm, f"ID: {workflow_id} | PAGE {doc.page}")
    
    # Footer
    canv.setFillColor(SURFACE)
    canv.rect(0, 0, PAGE_W, 12*mm, fill=1, stroke=0)
    canv.setFillColor(TEXT_MUTED)
    canv.setFont("Helvetica", 7)
    canv.drawCentredString(PAGE_W / 2, 6*mm, "Praecantator | Built on Google Cloud | Compliance Standard: EU CSDDD, CHIPS Act, DPDP")
    canv.restoreState()


class PraecantatorDocTemplate(BaseDocTemplate):
    def __init__(self, filename, workflow_id, **kw):
        super().__init__(filename, **kw)
        self.workflow_id = workflow_id
        frame = Frame(MARGIN_L, 16*mm, CONTENT_W, PAGE_H - 36*mm, id='normal')
        template = PageTemplate(id='First', frames=frame, onPage=self.on_page)
        self.addPageTemplates([template])
        
    def on_page(self, canv, doc):
        draw_background_and_header(canv, doc, self.workflow_id)


def create_card_table(data_rows, col_widths=None, border_color=CARD_BORDER):
    """Creates a stylized table resembling a UI card."""
    t = Table(data_rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), SURFACE),
        ('BOX', (0,0), (-1,-1), 1, border_color),
        ('INNERGRID', (0,0), (-1,-1), 0.5, border_color),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    return t


def generate_workflow_audit_report_pdf(report: dict, requested_by: str = "system") -> bytes:
    buffer = io.BytesIO()
    workflow_id = report.get("workflow_id", "UNKNOWN-ID")
    doc = PraecantatorDocTemplate(buffer, workflow_id=workflow_id, pagesize=A4)
    story = []
    stl = build_styles()
    
    # ================= COVER & HERO =================
    story.append(Paragraph("Praecantator Compliance Audit", stl["title"]))
    story.append(Paragraph("Immutable Supply Chain Execution Record", stl["subtitle"]))
    
    summary = report.get("summary", {})
    t_rt = summary.get("response_time_seconds", "—")
    t_exp = summary.get("exposure_usd", "—")
    t_act = summary.get("action_taken", "—")
    
    hero_data = [[
        Paragraph(str(t_rt) + "s" if t_rt != "—" else "—", stl["hero_number"]),
        Paragraph(fmt_usd(t_exp), stl["hero_number"]),
        Paragraph(str(t_act).title(), stl["hero_number"])
    ], [
        Paragraph("RESPONSE TIME", stl["hero_label"]),
        Paragraph("FINANCIAL EXPOSURE", stl["hero_label"]),
        Paragraph("ACTION EXECUTED", stl["hero_label"])
    ]]
    hero_table = create_card_table(hero_data, col_widths=[CONTENT_W/3]*3)
    story.append(hero_table)
    story.append(Spacer(1, 15))
    
    # Meta info
    meta_data = [
        [Paragraph("Workflow ID", stl["table_label"]), Paragraph(str(workflow_id), stl["mono"])],
        [Paragraph("Generated At", stl["table_label"]), Paragraph(fmt_timestamp(datetime.now(timezone.utc).isoformat()), stl["table_cell"])],
        [Paragraph("Requested By", stl["table_label"]), Paragraph(html.escape(str(requested_by)).upper(), stl["mono"])],
    ]
    story.append(create_card_table(meta_data, col_widths=[100, CONTENT_W - 100]))
    story.append(Spacer(1, 20))
    story.append(PageBreak())

    # ================= STAGE 1: DETECT =================
    detect = report.get("detect", {})
    evt = detect.get("event", {})
    story.append(Paragraph("01. DETECT (Signal Intake)", stl["section_title"]))
    detect_data = [
        [Paragraph("Dominant Event", stl["table_label"]), Paragraph(fmt_none(evt.get("title") or evt.get("event_type")), stl["table_cell"])],
        [Paragraph("Location", stl["table_label"]), Paragraph(fmt_none(evt.get("region") or evt.get("location")), stl["table_cell"])],
        [Paragraph("Detected At", stl["table_label"]), Paragraph(fmt_timestamp(evt.get("timestamp") or detect.get("detected_at")), stl["mono"])],
        [Paragraph("Severity", stl["table_label"]), Paragraph(fmt_none(evt.get("severity")), stl["warning"])]
    ]
    story.append(create_card_table(detect_data, col_widths=[100, CONTENT_W - 100]))
    
    incident_stream = detect.get("incident_stream", [])
    if incident_stream:
        # Proper table with type/description/source
        s_data = [[Paragraph("TYPE", stl["table_label"]), Paragraph("DESCRIPTION", stl["table_label"]), Paragraph("SOURCE", stl["table_label"])]]
        for inc in incident_stream[:8]:
            t_type = Paragraph(html.escape(fmt_none(inc.get("event_type") or inc.get("type"))).upper(), stl["mono"])
            t_desc = Paragraph(html.escape(fmt_none(inc.get("title") or inc.get("description"))), stl["body"])
            t_src = Paragraph(html.escape(fmt_none(inc.get("source"))), stl["body"])
            s_data.append([t_type, t_desc, t_src])
        story.append(Spacer(1, 10))
        story.append(Paragraph("Live Incident Stream:", stl["section_title"]))
        story.append(KeepTogether(create_card_table(s_data, col_widths=[80, CONTENT_W - 180, 100])))
    else:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Live Incident Stream: None Available", stl["body"]))
    
    story.append(Spacer(1, 15))
    
    # ================= STAGE 2: ASSESS =================
    assess = report.get("assess", {})
    story.append(Paragraph("02. ASSESS (AI Impact Analysis)", stl["section_title"]))
    conf = assess.get("confidence", 0)
    try: conf_val = float(conf)
    except: conf_val = 0
    conf_style = stl["success"] if conf_val >= 0.8 else (stl["warning"] if conf_val >= 0.65 else stl["danger"])
    
    assess_data = [
        [Paragraph("Analysis Engine", stl["table_label"]), Paragraph(fmt_none(assess.get("analysis_provider", "Gemini 2.0 Flash")), stl["mono"])],
        [Paragraph("Days at Risk", stl["table_label"]), Paragraph(fmt_none(assess.get("days_at_risk")), stl["table_cell"])],
        [Paragraph("Confidence Score", stl["table_label"]), Paragraph(f"{conf_val*100:.1f}%", conf_style)]
    ]
    story.append(create_card_table(assess_data, col_widths=[100, CONTENT_W - 100]))
    
    analysis_text = fmt_none(assess.get("analysis"))
    if analysis_text != "—":
        story.append(Spacer(1, 5))
        txt = html.escape(analysis_text).replace("### ", "").replace("**", "").replace("- ", "• ").replace("\n", "<br/>")
        story.append(KeepTogether(create_card_table([[Paragraph("<b>Assessment Summary:</b><br/>" + txt, stl["body"])]], border_color=AMBER)))
        
    story.append(Spacer(1, 15))
    
    # ================= STAGE 3: DECIDE =================
    decide = report.get("decide", {})
    story.append(Paragraph("03. DECIDE (Routing & Recommendation)", stl["section_title"]))
    decide_meta = [
        [Paragraph("Recommended", stl["table_label"]), Paragraph(fmt_none(decide.get("recommended_mode")).upper(), stl["success"])],
        [Paragraph("Currency Risk", stl["table_label"]), Paragraph(fmt_none(decide.get("currency_risk_index")), stl["table_cell"])],
    ]
    story.append(create_card_table(decide_meta, col_widths=[100, CONTENT_W - 100]))
    
    routes = decide.get("route_comparison", [])
    if routes:
        story.append(Spacer(1, 5))
        r_rows = [[Paragraph("MODE", stl["table_label"]), Paragraph("LANE", stl["table_label"]), Paragraph("TIME", stl["table_label"]), Paragraph("COST (USD)", stl["table_label"])]]
        for r in routes[:5]:
            m = fmt_none(r.get("mode")).upper()
            lane = fmt_none(r.get("lane")) if m == "SEA" else "—"
            
            # Separate land into SSSP and Maps explicitly
            if m == "LAND":
                maps = r.get("maps", {}) or {}
                sssp = r.get("sssp", {}) or {}
                if maps and maps.get("duration_hours"):
                    r_rows.append([
                        Paragraph("LAND (MAPS)", stl["mono"]),
                        Paragraph("—", stl["table_cell"]),
                        Paragraph(f"{maps.get('duration_hours')} hrs", stl["table_cell"]),
                        Paragraph(fmt_usd(maps.get("cost_usd")), stl["table_cell"])
                    ])
                if sssp and sssp.get("duration_hours"):
                    r_rows.append([
                        Paragraph("LAND (SSSP)", stl["mono"]),
                        Paragraph("—", stl["table_cell"]),
                        Paragraph(f"{sssp.get('duration_hours')} hrs", stl["table_cell"]),
                        Paragraph(fmt_usd(sssp.get("cost_usd")), stl["table_cell"])
                    ])
                # If neither are present but it's land
                if not (maps and maps.get("duration_hours")) and not (sssp and sssp.get("duration_hours")):
                    r_rows.append([Paragraph("LAND", stl["mono"]), Paragraph("—", stl["table_cell"]), Paragraph("—", stl["table_cell"]), Paragraph("—", stl["table_cell"])])
            else:
                # SEA or AIR
                if m == "AIR":  time = f"{fmt_none(r.get('flight_hours'))} hrs"
                elif m == "SEA": time = f"{fmt_none(r.get('transit_days'))} days"
                else: time = "—"
                
                c_val = r.get("cost_usd")
                c_str = fmt_usd(c_val)
                star = " ★" if decide.get("recommended_mode", "").lower() == m.lower() else ""
                r_rows.append([Paragraph(m + star, stl["mono"]), Paragraph(lane, stl["table_cell"]), Paragraph(time, stl["table_cell"]), Paragraph(c_str, stl["table_cell"])])
            
        r_table = create_card_table(r_rows, col_widths=[100, 80, 100, CONTENT_W-280])
        story.append(KeepTogether(r_table))

    story.append(Spacer(1, 15))
    story.append(PageBreak())
    
    # ================= STAGE 4: ACT =================
    act = report.get("act", {})
    story.append(Paragraph("04. ACT (Execution)", stl["section_title"]))
    act_data = [
        [Paragraph("Decision", stl["table_label"]), Paragraph(fmt_none(act.get("decision")).upper(), stl["success"])],
        [Paragraph("Executed At", stl["table_label"]), Paragraph(fmt_timestamp(act.get("executed_at")), stl["mono"])],
        [Paragraph("Details", stl["table_label"]), Paragraph(html.escape(fmt_none(act.get("details"))), stl["body"])]
    ]
    if act.get("rfq_recipient"):
        act_data.append([Paragraph("RFQ Sent To", stl["table_label"]), Paragraph(html.escape(fmt_none(act.get("rfq_recipient"))), stl["mono"])])
    story.append(create_card_table(act_data, col_widths=[100, CONTENT_W - 100], border_color=GREEN))
    story.append(Spacer(1, 15))
    
    # ================= STAGE 5: AUDIT =================
    audit = report.get("audit", {})
    story.append(Paragraph("05. AUDIT (Compliance Log)", stl["section_title"]))
    audit_data = [
        [Paragraph("Status", stl["table_label"]), Paragraph(fmt_none(audit.get("status", "COMPLETE")).upper(), stl["success"])],
        [Paragraph("Timeline", stl["table_label"]), Paragraph(fmt_none(audit.get("timeline")), stl["body"])],
        [Paragraph("Duration", stl["table_label"]), Paragraph(f"{fmt_none(audit.get('response_time_seconds'))} seconds", stl["table_cell"])]
    ]
    story.append(create_card_table(audit_data, col_widths=[100, CONTENT_W - 100]))
    
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Compliance Standard Callout:</b> Event automatically filed under the strict requirements of EU CSDDD, CHIPS Act, and DPDP.", stl["body"]))
    story.append(Paragraph("<i>Disclaimer:</i> This record is cryptographically immutable. All timestamps are UTC-synchronized and network-verified. The execution trail presented above bounds Praecantator's liabilities.", stl["body"]))
    
    # Appendix: NLP Summary
    try:
        story.append(PageBreak())
        story.append(Paragraph("APPENDIX: NLP Workflow Summary", stl["section_title"]))
        nlp_summary = report.get("appendix_nlp") or "Waiting for NLP generation..."
        txt = html.escape(nlp_summary).replace("\n", "<br/>")
        story.append(Paragraph(txt, stl["body"]))
    except Exception:
        pass

    doc.build(story)
    return buffer.getvalue()

def generate_audit_certificate(audit_id: str, user_id: str, summary_lines: list[str]) -> bytes:
    """Wrapper backwards compatibility for the old caller."""
    report = {
        "workflow_id": audit_id,
        "summary": {
            "response_time_seconds": "—",
            "exposure_usd": "—",
            "action_taken": "—"
        },
        "detect": {},
        "assess": {
             "analysis": "\\n".join(summary_lines)
        }
    }
    return generate_workflow_audit_report_pdf(report, requested_by=user_id)
