"""
Generate a SUDARSHAN UAV Operator License PDF.
Letterhead: Elysium Aerotech
Signed by:  Prerit Roshan, Project Director
"""

import os
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

# ── Colours ───────────────────────────────────────────────────
NAVY   = colors.HexColor("#1a237e")
CYAN   = colors.HexColor("#00b8d4")
GOLD   = colors.HexColor("#f9a825")
DARK   = colors.HexColor("#212121")
GREY   = colors.HexColor("#546e7a")
LGREY  = colors.HexColor("#eceff1")
WHITE  = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 22 * mm

def _style(name, **kw):
    return ParagraphStyle(name=name, **kw)

def generate_license(out_path: str, name: str, email: str,
                     score: int, total: int,
                     license_number: str,
                     issued_date: datetime.date,
                     valid_until: datetime.date) -> str:
    """
    Generate the operator license PDF and save to out_path.
    Returns out_path.
    """
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Elysium Aerotech Operator License — {name}",
        author="Elysium Aerotech",
    )

    # ── Styles ────────────────────────────────────────────────
    org_name   = _style("OrgName",  fontSize=26, leading=30, textColor=NAVY,
                        fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)
    org_sub    = _style("OrgSub",   fontSize=11, leading=14, textColor=CYAN,
                        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=2)
    org_tag    = _style("OrgTag",   fontSize=8,  leading=10, textColor=GREY,
                        fontName="Helvetica", alignment=TA_CENTER)
    ref_style  = _style("Ref",      fontSize=9,  leading=12, textColor=GREY,
                        fontName="Helvetica", alignment=TA_RIGHT, spaceAfter=2)
    date_style = _style("Date",     fontSize=9,  leading=12, textColor=GREY,
                        fontName="Helvetica", alignment=TA_LEFT, spaceAfter=2)
    cert_head  = _style("CertHead", fontSize=15, leading=19, textColor=NAVY,
                        fontName="Helvetica-Bold", alignment=TA_CENTER,
                        spaceBefore=6, spaceAfter=4)
    cert_sub   = _style("CertSub",  fontSize=10, leading=13, textColor=GREY,
                        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=10)
    body_c     = _style("BodyC",    fontSize=10, leading=15, textColor=DARK,
                        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4)
    candidate  = _style("Cand",     fontSize=22, leading=26, textColor=NAVY,
                        fontName="Helvetica-Bold", alignment=TA_CENTER,
                        spaceBefore=4, spaceAfter=4)
    body_j     = _style("BodyJ",    fontSize=10, leading=15, textColor=DARK,
                        fontName="Helvetica", alignment=TA_JUSTIFY,
                        spaceBefore=4, spaceAfter=4)
    small_c    = _style("SmC",      fontSize=9,  leading=12, textColor=GREY,
                        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=2)
    sig_name   = _style("SigName",  fontSize=11, leading=14, textColor=NAVY,
                        fontName="Helvetica-Bold", alignment=TA_CENTER)
    sig_title  = _style("SigTitle", fontSize=9,  leading=12, textColor=GREY,
                        fontName="Helvetica", alignment=TA_CENTER)
    footer_s   = _style("Footer",   fontSize=7.5, textColor=GREY,
                        fontName="Helvetica", alignment=TA_CENTER)

    pct = int(score / total * 100)
    story = []

    # ── Header band ───────────────────────────────────────────
    hdr_data = [[
        Paragraph("ELYSIUM AEROTECH", org_name),
    ]]
    hdr = Table(hdr_data, colWidths=[PAGE_W - 2 * MARGIN])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), NAVY),
        ("TOPPADDING",  (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
    ]))
    # Override text colour inside table — use white
    org_name_w = _style("OrgNameW", fontSize=26, leading=30, textColor=WHITE,
                        fontName="Helvetica-Bold", alignment=TA_CENTER)
    hdr_data2 = [[Paragraph("ELYSIUM AEROTECH", org_name_w)]]
    hdr2 = Table(hdr_data2, colWidths=[PAGE_W - 2 * MARGIN])
    hdr2.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
    ]))
    story.append(hdr2)

    # Sub-header
    story.append(Paragraph("Advanced Unmanned Aerial Systems", org_sub))
    story.append(Paragraph("Certified Hardware · Research & Development · India", org_tag))
    story.append(Spacer(1, 6 * mm))

    # Gold divider line
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6))

    # Ref / date row
    ref_date_data = [[
        Paragraph(f"Date: {issued_date.strftime('%d %B %Y')}", date_style),
        Paragraph(f"Ref: {license_number}", ref_style),
    ]]
    ref_row = Table(ref_date_data,
                    colWidths=[(PAGE_W-2*MARGIN)*0.5, (PAGE_W-2*MARGIN)*0.5])
    ref_row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(ref_row)
    story.append(Spacer(1, 4 * mm))

    # Certificate heading
    story.append(Paragraph("CERTIFICATE OF COMPETENCY", cert_head))
    story.append(Paragraph(
        "Unmanned Aerial Vehicle Operator License — SUDARSHAN UAV System",
        cert_sub))

    story.append(HRFlowable(width="80%", thickness=0.5, color=LGREY,
                             hAlign="CENTER", spaceAfter=6))

    # Body text
    story.append(Paragraph("This is to certify that", body_c))
    story.append(Paragraph(name.upper(), candidate))
    story.append(Paragraph(f"({email})", small_c))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        f"has successfully completed the <b>SUDARSHAN UAV Operator Certification Examination</b> "
        f"conducted by Elysium Aerotech, achieving a score of "
        f"<b>{score} out of {total} ({pct}%)</b> on "
        f"<b>{issued_date.strftime('%d %B %Y')}</b>.",
        body_j))

    story.append(Paragraph(
        "The examination covered: hardware wiring and component identification, "
        "flight controller logic and PID systems, communication protocols, "
        "safety procedures and dead-man switch operation, and operational procedures "
        "for the SUDARSHAN UAV platform.",
        body_j))

    story.append(Spacer(1, 3 * mm))

    # License details box
    lic_data = [
        ["LICENSE NUMBER",  license_number],
        ["ISSUED TO",       name],
        ["ISSUED BY",       "Elysium Aerotech"],
        ["DATE OF ISSUE",   issued_date.strftime("%d %B %Y")],
        ["VALID UNTIL",     valid_until.strftime("%d %B %Y")],
        ["SYSTEM",          "SUDARSHAN UAV v1.2"],
        ["TEST SCORE",      f"{score}/{total}  ({pct}%)"],
    ]
    lic_table = Table(lic_data,
                      colWidths=[55*mm, PAGE_W - 2*MARGIN - 55*mm])
    lic_table.setStyle(TableStyle([
        ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
        ("FONTNAME",      (1,0),(1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("TEXTCOLOR",     (0,0),(0,-1), NAVY),
        ("TEXTCOLOR",     (1,0),(1,-1), DARK),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LGREY]),
        ("GRID",          (0,0),(-1,-1), 0.3, GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 7),
    ]))
    story.append(lic_table)
    story.append(Spacer(1, 4 * mm))

    # Conditions
    story.append(Paragraph("<b>Conditions of this License:</b>", body_j))
    conditions = [
        "This license is valid for one (1) year from the date of issue.",
        "The holder must operate the SUDARSHAN UAV within the limits defined in the Operator Manual.",
        "Any structural or firmware modification to the drone voids this certification.",
        "The holder is responsible for compliance with all applicable local aviation regulations.",
        "This license is non-transferable and remains the property of Elysium Aerotech.",
    ]
    for c in conditions:
        story.append(Paragraph(f"  •  {c}", _style(
            "Cond", fontSize=9, leading=13, textColor=DARK,
            fontName="Helvetica", leftIndent=8, spaceAfter=2)))

    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=4))

    # Signature section
    sig_left  = [
        Paragraph("Authorised and issued by:", _style(
            "SL", fontSize=9, textColor=GREY, fontName="Helvetica",
            alignment=TA_LEFT, spaceAfter=12)),
        Paragraph("_" * 32, _style(
            "SL2", fontSize=10, textColor=NAVY, fontName="Helvetica",
            alignment=TA_LEFT, spaceAfter=4)),
        Paragraph("PRERIT ROSHAN", sig_name),
        Paragraph("Project Director", sig_title),
        Paragraph("Elysium Aerotech", sig_title),
    ]
    sig_right = [
        Paragraph("Stamp / Seal:", _style(
            "SR", fontSize=9, textColor=GREY, fontName="Helvetica",
            alignment=TA_CENTER, spaceAfter=4)),
        # Circular seal placeholder
        _SealFlowable(radius=18 * mm),
    ]

    sig_data = [[sig_left, sig_right]]
    sig_t = Table(sig_data,
                  colWidths=[(PAGE_W-2*MARGIN)*0.55, (PAGE_W-2*MARGIN)*0.45])
    sig_t.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(0,-1), 0),
        ("RIGHTPADDING", (0,0),(0,-1), 10),
    ]))
    story.append(sig_t)

    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=4))
    story.append(Paragraph(
        "Elysium Aerotech  ·  Advanced Unmanned Aerial Systems  ·  India  "
        "·  This document is system-generated and digitally validated.",
        footer_s))

    # ── Watermark / border drawn on canvas ───────────────────
    doc.build(story, onFirstPage=_draw_border, onLaterPages=_draw_border)
    return out_path


# ── Seal placeholder flowable ─────────────────────────────────
from reportlab.platypus import Flowable

class _SealFlowable(Flowable):
    def __init__(self, radius):
        super().__init__()
        self.radius = radius
        self.width  = radius * 2
        self.height = radius * 2

    def draw(self):
        r = self.radius
        c = self.canv
        c.setStrokeColor(NAVY)
        c.setFillColor(LGREY)
        c.setLineWidth(1.5)
        c.circle(r, r, r, fill=1)
        c.setStrokeColor(NAVY)
        c.setFillColor(NAVY)
        c.setLineWidth(0.5)
        c.circle(r, r, r * 0.85, fill=0)
        # Text inside seal
        c.setFont("Helvetica-Bold", 5.5)
        c.setFillColor(NAVY)
        c.drawCentredString(r, r + 7, "ELYSIUM")
        c.drawCentredString(r, r + 1, "AEROTECH")
        c.setFont("Helvetica", 4.5)
        c.drawCentredString(r, r - 6, "CERTIFIED OPERATOR")
        c.setFont("Helvetica-Bold", 4)
        c.drawCentredString(r, r - 12, "SUDARSHAN UAV")


def _draw_border(canvas, doc):
    """Draw a decorative page border."""
    w, h = A4
    canvas.saveState()
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(3)
    canvas.rect(8*mm, 8*mm, w - 16*mm, h - 16*mm)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(1)
    canvas.rect(10*mm, 10*mm, w - 20*mm, h - 20*mm)
    canvas.restoreState()
