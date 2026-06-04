#!/usr/bin/env python3
"""
SUDARSHAN UAV Project — Generate all 5 professional PDF documents.
Run: python3 gen_docs.py
"""

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ─── Colour palette ────────────────────────────────────────────────────────────
NAVY  = colors.HexColor("#1a237e")
CYAN  = colors.HexColor("#00b8d4")
DARK  = colors.HexColor("#212121")
LGREY = colors.HexColor("#eceff1")
RED   = colors.HexColor("#c62828")
GREEN = colors.HexColor("#2e7d32")
AMBER = colors.HexColor("#e65100")
WHITE = colors.white
LIGHT_CYAN = colors.HexColor("#e0f7fa")
LIGHT_NAVY = colors.HexColor("#283593")

OUT_DIR = "/home/user/Aerotech2.0/SUDARSHAN-RADHA/Docs"
os.makedirs(OUT_DIR, exist_ok=True)

# ─── Shared style helpers ──────────────────────────────────────────────────────

def get_styles():
    styles = getSampleStyleSheet()

    def add_style(name, **kwargs):
        if name not in styles.byName:
            styles.add(ParagraphStyle(name=name, **kwargs))
        return styles[name]

    add_style("DocTitle",
              fontName="Helvetica-Bold", fontSize=22, textColor=WHITE,
              alignment=TA_CENTER, spaceAfter=6)
    add_style("DocSubtitle",
              fontName="Helvetica", fontSize=13, textColor=LIGHT_CYAN,
              alignment=TA_CENTER, spaceAfter=4)
    add_style("SectionHeader",
              fontName="Helvetica-Bold", fontSize=13, textColor=WHITE,
              backColor=NAVY, spaceBefore=14, spaceAfter=6,
              leftIndent=6, rightIndent=6, leading=18)
    add_style("SubHeader",
              fontName="Helvetica-Bold", fontSize=11, textColor=NAVY,
              spaceBefore=10, spaceAfter=4)
    add_style("BodyText2",
              fontName="Helvetica", fontSize=9.5, textColor=DARK,
              leading=14, spaceAfter=4)
    add_style("BulletText2",
              fontName="Helvetica", fontSize=9.5, textColor=DARK,
              leading=14, leftIndent=14, bulletIndent=4, spaceAfter=2)
    add_style("QuestionText",
              fontName="Helvetica-Bold", fontSize=10, textColor=DARK,
              leading=14, spaceAfter=2, spaceBefore=6)
    add_style("AnswerText",
              fontName="Helvetica", fontSize=9.5, textColor=DARK,
              leading=13, leftIndent=16, spaceAfter=1)
    add_style("RedBold",
              fontName="Helvetica-Bold", fontSize=10, textColor=RED,
              spaceBefore=8, spaceAfter=4, leading=14)
    add_style("GreenNote",
              fontName="Helvetica-BoldOblique", fontSize=9, textColor=GREEN,
              spaceAfter=4, leading=12)
    add_style("FooterStyle",
              fontName="Helvetica", fontSize=8, textColor=colors.grey,
              alignment=TA_CENTER)
    add_style("CertTitle",
              fontName="Helvetica-Bold", fontSize=20, textColor=NAVY,
              alignment=TA_CENTER, spaceBefore=20, spaceAfter=10)
    add_style("CertBody",
              fontName="Helvetica", fontSize=12, textColor=DARK,
              alignment=TA_CENTER, spaceAfter=8, leading=20)
    add_style("TableHeader",
              fontName="Helvetica-Bold", fontSize=9, textColor=WHITE,
              alignment=TA_CENTER)
    add_style("CellText",
              fontName="Helvetica", fontSize=8.5, textColor=DARK,
              leading=12)
    add_style("ModuleTitle",
              fontName="Helvetica-Bold", fontSize=14, textColor=WHITE,
              alignment=TA_CENTER, spaceAfter=6)
    add_style("ExerciseHeader",
              fontName="Helvetica-Bold", fontSize=10, textColor=AMBER,
              spaceBefore=10, spaceAfter=4)
    add_style("SmallNote",
              fontName="Helvetica-Oblique", fontSize=8.5, textColor=colors.grey,
              spaceAfter=3, leading=12)
    add_style("ManualHeading1",
              fontName="Helvetica-Bold", fontSize=15, textColor=NAVY,
              spaceBefore=16, spaceAfter=6, borderPad=4)
    add_style("ManualHeading2",
              fontName="Helvetica-Bold", fontSize=11, textColor=LIGHT_NAVY,
              spaceBefore=10, spaceAfter=4)
    add_style("ChecklistItem",
              fontName="Helvetica", fontSize=9.5, textColor=DARK,
              leading=14, leftIndent=6, spaceAfter=2)
    return styles


def header_banner(title, subtitle=None, c_width=A4[0]):
    """Return a Table that acts as a coloured title banner."""
    title_p = Paragraph(title, get_styles()["DocTitle"])
    rows = [[title_p]]
    if subtitle:
        sub_p = Paragraph(subtitle, get_styles()["DocSubtitle"])
        rows.append([sub_p])
    tbl = Table(rows, colWidths=[c_width - 2*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return tbl


def section_header(text, styles):
    return Paragraph(text, styles["SectionHeader"])


def cyan_rule():
    return HRFlowable(width="100%", thickness=2, color=CYAN, spaceAfter=6, spaceBefore=2)


def build_table(headers, rows, col_widths, alt_rows=True):
    """Build a styled table with navy header row."""
    header_row = [Paragraph(h, get_styles()["TableHeader"]) for h in headers]
    data = [header_row]
    cell_style = get_styles()["CellText"]
    for row in rows:
        data.append([Paragraph(str(c), cell_style) for c in row])

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 9),
        ("ALIGN",        (0,0), (-1,-1), "LEFT"),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#b0bec5")),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ]
    if alt_rows:
        for i in range(2, len(data), 2):
            style_cmds.append(("BACKGROUND", (0,i), (-1,i), LGREY))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def page_footer(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.grey)
    canvas_obj.drawCentredString(A4[0]/2, 1.5*cm,
        f"SUDARSHAN UAV Project  —  Confidential  —  Page {canvas_obj.getPageNumber()}")
    canvas_obj.setStrokeColor(CYAN)
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(2*cm, 1.9*cm, A4[0]-2*cm, 1.9*cm)
    canvas_obj.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
# PDF 1 — OPERATOR QUIZ
# ══════════════════════════════════════════════════════════════════════════════

def build_quiz():
    path = os.path.join(OUT_DIR, "SUDARSHAN_OPERATOR_QUIZ.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.2*cm, bottomMargin=2.5*cm)
    styles = get_styles()
    story = []

    story.append(header_banner("SUDARSHAN UAV — OPERATOR CERTIFICATION QUIZ",
                               "25-Question Multiple Choice  |  Time Allowed: 40 Minutes"))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Name: ________________________________   Date: ________________   Score: _____ / 25",
        styles["BodyText2"]))
    story.append(Paragraph(
        "Instructions: Circle the single best answer for each question. No open-book unless directed by instructor.",
        styles["SmallNote"]))
    story.append(cyan_rule())

    # ── Question data ─────────────────────────────────────────────────────────
    sections = [
        ("Section 1 — Hardware & Wiring", [
            ("Q1.", "Which I2C address does MPU6050 use when AD0 = LOW?",
             ["(a) 0x40", "(b) 0x68 ✓", "(c) 0x69", "(d) 0x76"], "b"),
            ("Q2.", "What does the Mega → ESP32 voltage divider accomplish?",
             ["(a) Boost 3.3 V → 5 V", "(b) Convert 5 V → 3.3 V ✓", "(c) Filter noise", "(d) Regulate power"], "b"),
            ("Q3.", "Which PCA9685 channel drives the Front-Right motor?",
             ["(a) CH0", "(b) CH1 ✓", "(c) CH2", "(d) CH3"], "b"),
            ("Q4.", "Which Uno pins connect to the PCA9685 I2C bus?",
             ["(a) D2/D3", "(b) D18/D19", "(c) A4/A5 ✓", "(d) D6/D7"], "c"),
            ("Q5.", "Why must Uno Pins 0 and 1 be disconnected before USB flashing?",
             ["(a) They carry too much current", "(b) They are shared with the USB-serial adapter ✓",
              "(c) They can damage the PCA9685", "(d) They interfere with I2C"], "b"),
        ]),
        ("Section 2 — Flight Controller", [
            ("Q6.", "What is the Mega FC control-loop rate?",
             ["(a) 50 Hz", "(b) 100 Hz", "(c) 200 Hz", "(d) 250 Hz ✓"], "d"),
            ("Q7.", "CF_ALPHA = 0.98 means the complementary filter applies:",
             ["(a) 98% accelerometer, 2% gyroscope", "(b) 98% gyroscope, 2% accelerometer ✓",
              "(c) 98% sonar", "(d) It is a sampling ratio"], "b"),
            ("Q8.", "The drone spins CW continuously with no yaw command. What is the correct fix?",
             ["(a) Increase Ki_yaw", "(b) Swap all propellers",
              "(c) Change IMU_YAW_SIGN to −1 ✓", "(d) Decrease CF_ALPHA"], "c"),
            ("Q9.", "What happens when sonar reads < 8 cm for 6 consecutive counts during LAND?",
             ["(a) Drone disarms immediately ✓", "(b) Drone hovers at ground level",
              "(c) Slow hover begins at 30 cm", "(d) LAND mode continues"], "a"),
            ("Q10.", "Which command is BLOCKED while the drone is armed?",
             ["(a) HOVER", "(b) OVERRIDE", "(c) LAND", "(d) SET_MOTOR_MAP ✓"], "d"),
        ]),
        ("Section 3 — Communications", [
            ("Q11.", "What is the motor packet format from Mega → Uno?",
             ["(a) JSON over UART", "(b) 10-byte binary + XOR checksum ✓",
              "(c) 8-byte CAN frame", "(d) PWM pulses"], "b"),
            ("Q12.", "Which TCP port does the Python GCS use to connect to the ESP32?",
             ["(a) 80", "(b) 81", "(c) 5760 ✓", "(d) 8080"], "c"),
            ("Q13.", "At what rate does the FC send telemetry to the GCS?",
             ["(a) 1 Hz", "(b) 5 Hz", "(c) 10 Hz ✓", "(d) 25 Hz"], "c"),
            ("Q14.", "Where must the AES encryption key be stored?",
             ["(a) In the git repository", "(b) In credentials.h / credentials.py only, never committed ✓",
              "(c) In the project PDF", "(d) Sent inside every TCP packet"], "b"),
            ("Q15.", "The XOR checksum covers which bytes of the 10-byte motor packet?",
             ["(a) All 10 bytes", "(b) Bytes 0–8", "(c) Bytes 1–8 ✓", "(d) Bytes 1–9"], "c"),
        ]),
        ("Section 4 — Safety & Emergency", [
            ("Q16.", "How many independent DMS (Dead-Man Switch) layers are implemented?",
             ["(a) 1", "(b) 2", "(c) 3 ✓", "(d) 4"], "c"),
            ("Q17.", "What is the FC-side DMS timeout?",
             ["(a) 10 s", "(b) 20 s", "(c) 30 s ✓", "(d) 60 s"], "c"),
            ("Q18.", "A battery voltage of 9.9 V triggers which action?",
             ["(a) Warning flag only", "(b) Telemetry flag only",
              "(c) Automatic LAND command ✓", "(d) Immediate motor cut"], "c"),
            ("Q19.", "After a KILL command is executed, to resume flying you must:",
             ["(a) Send ARM", "(b) Send DISARM then ARM",
              "(c) Power-cycle the drone ✓", "(d) Press HOVER"], "c"),
            ("Q20.", "sonar_ok = 0 is reported during a hover. The correct operator action is:",
             ["(a) Continue normally", "(b) Increase altitude slowly",
              "(c) Land manually immediately ✓", "(d) Switch to OVERRIDE mode"], "c"),
        ]),
        ("Section 5 — Operations", [
            ("Q21.", "What is the correct power-on sequence?",
             ["(a) ESP32 first",
              "(b) Mega + Uno first, wait for ESC beeps, then ESP32 ✓",
              "(c) All components simultaneously", "(d) Phone / GCS first"], "b"),
            ("Q22.", "What must be done before executing MOTOR_TEST?",
             ["(a) ARM the drone", "(b) Remove all propellers ✓",
              "(c) Connect phone GPS", "(d) Enable AES encryption"], "b"),
            ("Q23.", "What is the Web GCS session priority override code?",
             ["(a) 0000", "(b) 980752", "(c) 1410 ✓", "(d) admin"], "c"),
            ("Q24.", "What is the minimum safety perimeter before executing ARM outdoors?",
             ["(a) 1 m", "(b) 5 m", "(c) 10 m ✓", "(d) 20 m"], "c"),
            ("Q25.", "PRESET mission segments use which positional reference?",
             ["(a) GPS coordinates",
              "(b) Bearing + distance relative to IMU heading ✓",
              "(c) X/Y grid coordinates", "(d) Compass waypoints"], "b"),
        ]),
    ]

    answers = {}
    q_num = 1
    for sec_title, questions in sections:
        story.append(KeepTogether([
            section_header(sec_title, styles),
            Spacer(1, 4),
        ]))
        for q_id, q_text, choices, correct in questions:
            answers[q_num] = correct.upper()
            block = [
                Paragraph(f"{q_id} {q_text}", styles["QuestionText"]),
            ]
            for ch in choices:
                block.append(Paragraph(ch, styles["AnswerText"]))
            block.append(Spacer(1, 4))
            story.append(KeepTogether(block))
            q_num += 1
        story.append(Spacer(1, 6))

    # ── Answer Key ────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(header_banner("ANSWER KEY — INSTRUCTOR COPY",
                               "Do Not Distribute to Candidates"))
    story.append(Spacer(1, 12))

    key_rows = []
    for i in range(1, 26, 5):
        row = []
        for j in range(i, min(i+5, 26)):
            row.append(f"Q{j}: {answers[j].upper()}")
        key_rows.append(row)

    key_data = [["Q1–Q5", "Q6–Q10", "Q11–Q15", "Q16–Q20", "Q21–Q25"]]
    for row in key_rows:
        # pad if needed
        while len(row) < 5:
            row.append("")
        key_data.append(row)

    # Flatten into a readable table
    flat_data = [["No.", "Answer", "No.", "Answer", "No.", "Answer", "No.", "Answer", "No.", "Answer"]]
    col_answers = [[], [], [], [], []]
    for n in range(1, 26):
        col_answers[(n-1) % 5].append((n, answers[n].upper()))

    for i in range(5):
        row = []
        for col in col_answers:
            if i < len(col):
                row.extend([str(col[i][0]), col[i][1]])
            else:
                row.extend(["", ""])
        flat_data.append(row)

    cw = [1.2*cm, 1.5*cm] * 5
    ak_tbl = Table(flat_data, colWidths=cw)
    ak_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#b0bec5")),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("BACKGROUND",   (1,1), (1,-1), LIGHT_CYAN),
        ("BACKGROUND",   (3,1), (3,-1), LIGHT_CYAN),
        ("BACKGROUND",   (5,1), (5,-1), LIGHT_CYAN),
        ("BACKGROUND",   (7,1), (7,-1), LIGHT_CYAN),
        ("BACKGROUND",   (9,1), (9,-1), LIGHT_CYAN),
        ("FONTNAME",     (1,1), (1,-1), "Helvetica-Bold"),
        ("FONTNAME",     (3,1), (3,-1), "Helvetica-Bold"),
        ("FONTNAME",     (5,1), (5,-1), "Helvetica-Bold"),
        ("FONTNAME",     (7,1), (7,-1), "Helvetica-Bold"),
        ("FONTNAME",     (9,1), (9,-1), "Helvetica-Bold"),
    ]))
    story.append(ak_tbl)
    story.append(Spacer(1, 16))

    # Scoring guide
    story.append(section_header("Scoring Guide", styles))
    score_rows = [
        ["23 – 25", "CERTIFIED OPERATOR", "May operate SUDARSHAN UAV independently"],
        ["18 – 22", "SUPERVISED ONLY",    "Must fly under certified operator supervision"],
        ["< 18",    "REQUIRES RETRAINING","Must complete refresher training before re-assessment"],
    ]
    score_tbl = build_table(
        ["Score Range", "Status", "Notes"],
        score_rows,
        [3*cm, 4.5*cm, 9*cm]
    )
    story.append(score_tbl)

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"  [OK] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# PDF 2 — TRAINING COURSE
# ══════════════════════════════════════════════════════════════════════════════

def build_training_course():
    path = os.path.join(OUT_DIR, "SUDARSHAN_TRAINING_COURSE.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.2*cm, bottomMargin=2.5*cm)
    styles = get_styles()
    story = []

    story.append(header_banner("SUDARSHAN UAV — OPERATOR TRAINING COURSE",
                               "Five-Module Structured Curriculum  |  Issue 1.0"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This course prepares operators to safely configure, operate, and maintain the "
        "SUDARSHAN quadrotor UAV system. Completion of all five modules and a score ≥ 23/25 "
        "on the Operator Certification Quiz is required for independent flight operations.",
        styles["BodyText2"]))
    story.append(cyan_rule())

    # ── Helper for a module banner ─────────────────────────────────────────────
    def module_banner(num, title):
        p = Paragraph(f"MODULE {num}:  {title}", styles["ModuleTitle"])
        tbl = Table([[p]], colWidths=[A4[0]-4*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), LIGHT_NAVY),
            ("TOPPADDING",    (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ]))
        return tbl

    def quiz_table(qs):
        rows = [[f"Q{i+1}.", q] for i, q in enumerate(qs)]
        tbl = Table(rows, colWidths=[1*cm, A4[0]-5.5*cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("VALIGN",       (0,0), (-1,-1), "TOP"),
            ("BACKGROUND",   (0,0), (-1,-1), LGREY),
            ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#cfd8dc")),
        ]))
        return tbl

    # ── MODULE 1 ──────────────────────────────────────────────────────────────
    story.append(module_banner(1, "System Orientation"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Learning Objectives", styles["SubHeader"]))
    for obj in [
        "Identify all major hardware components and their roles in the SUDARSHAN system.",
        "Trace the power flow from LiPo battery through BEC, ESCs, and microcontrollers.",
        "Describe the three-layer software architecture (FC / Uno driver / ESP32 gateway).",
    ]:
        story.append(Paragraph(f"• {obj}", styles["BulletText2"]))

    story.append(Paragraph("Content Overview", styles["SubHeader"]))
    story.append(Paragraph(
        "The SUDARSHAN quadrotor uses an Arduino Mega as the primary Flight Controller (FC), "
        "an Arduino Uno as the motor driver board, and an ESP32 as the wireless gateway. "
        "A 3S LiPo (11.1 V nominal) powers four brushless motors via individual ESCs. "
        "Power is distributed through a PDB; a 5 V BEC supplies the microcontrollers. "
        "An MPU-6050 IMU provides roll/pitch/yaw data via I2C. An HC-SR04 ultrasonic sensor "
        "measures altitude up to ~2 m. The PCA9685 PWM driver on the Uno board controls "
        "ESC signal lines on channels CH0–CH3.", styles["BodyText2"]))
    story.append(Paragraph(
        "Layer Architecture: Layer 1 (FC / Mega) runs the PID control loop at 250 Hz. "
        "Layer 2 (Uno) receives 10-byte motor packets and outputs calibrated PWM to ESCs. "
        "Layer 3 (ESP32) bridges TCP Wi-Fi commands from the GCS to the Mega via UART "
        "with a 5 V → 3.3 V voltage divider on the Mega TX line.", styles["BodyText2"]))

    story.append(Paragraph("Exercise 1 — Wiring Table Completion", styles["ExerciseHeader"]))
    story.append(Paragraph(
        "Fill in the blank cells in the table below using the SUDARSHAN wiring diagram.",
        styles["SmallNote"]))
    wire_rows = [
        ["MPU-6050 SDA",  "Mega A4",   "I2C Data",         ""],
        ["MPU-6050 SCL",  "Mega A5",   "I2C Clock",        ""],
        ["PCA9685 SDA",   "Uno A4",    "I2C Data",         ""],
        ["PCA9685 SCL",   "Uno A5",    "I2C Clock",        ""],
        ["Mega TX1",      "_______",   "Motor commands",   "UART 115200"],
        ["Uno RX",        "Mega TX1",  "_______",          "UART 115200"],
        ["ESP32 RX",      "_______",   "GCS commands",     "Voltage divider"],
        ["Mega TX2",      "_______",   "ESP32 bridge",     ""],
        ["HC-SR04 TRIG",  "Mega D9",   "_______",          ""],
        ["HC-SR04 ECHO",  "Mega D10",  "Ultrasonic echo",  ""],
    ]
    story.append(build_table(
        ["Signal / Component", "Connected To", "Function", "Notes"],
        wire_rows, [4*cm, 4*cm, 4.5*cm, 3.5*cm]))

    story.append(Paragraph("Module 1 Quiz", styles["SubHeader"]))
    story.append(quiz_table([
        "The MPU-6050 communicates with the Mega via which protocol and pins?",
        "Name the three software layers of the SUDARSHAN architecture and the microcontroller responsible for each.",
        "What is the purpose of the 5 V → 3.3 V voltage divider on the Mega TX2 line?",
    ]))
    story.append(Spacer(1, 10))

    # ── MODULE 2 ──────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(module_banner(2, "GCS Operation"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Learning Objectives", styles["SubHeader"]))
    for obj in [
        "Connect the GCS laptop to the SUDARSHAN Wi-Fi access point.",
        "Navigate all five GCS tabs and describe the purpose of each.",
        "Interpret all telemetry fields and the status bar indicators.",
    ]:
        story.append(Paragraph(f"• {obj}", styles["BulletText2"]))

    story.append(Paragraph("Content Overview", styles["SubHeader"]))
    story.append(Paragraph(
        "The Python GCS application connects to the ESP32 at TCP 192.168.4.1:5760. "
        "The interface is organised into five functional tabs:", styles["BodyText2"]))
    tab_rows = [
        ["FLIGHT",    "ARM / DISARM, HOVER, LAND, KILL commands; live telemetry panel"],
        ["PRESET",    "Load, edit, and transmit PRESET mission segments (bearing + distance)"],
        ["PREFLIGHT", "Run MOTOR_TEST, IMU preflight check, sonar sanity test"],
        ["NAV",       "IMUMISSION start / abort, override waypoint injection"],
        ["GUIDE",     "Manual OVERRIDE mode with on-screen virtual joystick"],
    ]
    story.append(build_table(["Tab", "Purpose"], tab_rows, [3*cm, 13*cm]))
    story.append(Paragraph(
        "Key telemetry fields: roll_deg, pitch_deg, yaw_deg (IMU angles), alt_cm "
        "(sonar altitude), bat_mv (battery mV), sonar_ok (1=valid), state (IDLE/ARMED/"
        "HOVER/LAND/KILL), dms_countdown (seconds until DMS timeout).", styles["BodyText2"]))

    story.append(Paragraph("Exercise 2 — Simulated GCS Session Checklist", styles["ExerciseHeader"]))
    story.append(Paragraph(
        "Work through the following 10-step procedure and tick each step as completed.",
        styles["SmallNote"]))
    steps = [
        "Connect laptop Wi-Fi to SSID 'SUDARSHAN_AP'",
        "Launch GCS application — verify connection indicator turns GREEN",
        "Open PREFLIGHT tab — run MOTOR_TEST with props removed",
        "Confirm all 4 motor channels respond in sequence (0→25% duty)",
        "Open PREFLIGHT tab — run IMU_CHECK; confirm pass (green)",
        "Open PREFLIGHT tab — run SONAR_CHECK; confirm alt_cm > 0",
        "Check bat_mv > 10500 mV in telemetry panel",
        "Open FLIGHT tab — issue ARM command; confirm state = ARMED",
        "Issue HOVER; observe alt_cm stabilises within ±5 cm",
        "Issue LAND; confirm state transitions LAND → DISARMED",
    ]
    chk_data = [[f"☐  Step {i+1}.", s] for i, s in enumerate(steps)]
    chk_tbl = Table(chk_data, colWidths=[2.5*cm, 13.5*cm])
    chk_tbl.setStyle(TableStyle([
        ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#cfd8dc")),
    ]))
    story.append(chk_tbl)

    story.append(Paragraph("Module 2 Quiz", styles["SubHeader"]))
    story.append(quiz_table([
        "Which TCP port and IP address does the GCS use to communicate with the ESP32?",
        "Describe the difference between the PRESET tab and the NAV tab.",
        "What telemetry field indicates whether the sonar sensor is providing valid data?",
    ]))
    story.append(Spacer(1, 10))

    # ── MODULE 3 ──────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(module_banner(3, "Flight Operations"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Learning Objectives", styles["SubHeader"]))
    for obj in [
        "Execute the full pre-flight checklist without reference material.",
        "Perform ARM, HOVER, controlled LAND, and emergency procedures correctly.",
        "Select the appropriate emergency command for each abnormal condition.",
    ]:
        story.append(Paragraph(f"• {obj}", styles["BulletText2"]))

    story.append(Paragraph("Pre-Flight Checklist", styles["SubHeader"]))
    pf_items = [
        ("MECHANICAL", ["All 4 props tight and correct orientation (CW/CCW)",
                        "Frame arms secure, no cracks", "Landing gear intact",
                        "Motor shafts free — no binding"]),
        ("ELECTRICAL", ["LiPo charged (> 11.8 V = 100%)", "Balance connector checked",
                        "All connectors fully seated", "No damaged wiring"]),
        ("FIRMWARE",   ["Mega FC serial shows READY", "Uno serial shows READY",
                        "ESP32 AP visible in Wi-Fi list"]),
        ("GCS",        ["GCS connected (green indicator)", "MOTOR_TEST passed (no props)",
                        "IMU preflight passed", "Sonar sanity passed",
                        "bat_mv > 10 500 mV confirmed"]),
        ("AREA",       ["10 m safety perimeter clear of persons", "Wind < 5 m/s",
                        "No overhead obstructions within flight path"]),
    ]
    for cat, items in pf_items:
        story.append(Paragraph(cat, styles["ManualHeading2"]))
        for item in items:
            story.append(Paragraph(f"☐  {item}", styles["ChecklistItem"]))

    story.append(Paragraph("Emergency Decision Table", styles["ExerciseHeader"]))
    story.append(Paragraph(
        "Exercise 3: Given each telemetry state below, choose and record the correct command.",
        styles["SmallNote"]))
    emer_rows = [
        ["Uncommanded CW yaw rotation, state = HOVER",    "_______________", "KILL / check props"],
        ["bat_mv = 9800, state = HOVER",                  "_______________", "Auto-LAND triggered"],
        ["sonar_ok = 0, state = HOVER",                   "_______________", "LAND manually"],
        ["No GCS telemetry for 10 s, state = ARMED",      "_______________", "DMS triggers LAND"],
        ["Drone drifts rapidly toward obstacle, HOVER",   "_______________", "KILL then power-cycle"],
    ]
    story.append(build_table(
        ["Scenario", "Your Command", "Reference Answer"],
        emer_rows, [6*cm, 4.5*cm, 5.5*cm]))

    story.append(Paragraph("Module 3 Quiz", styles["SubHeader"]))
    story.append(quiz_table([
        "At what battery voltage does the FC automatically issue a LAND command?",
        "If the drone begins drifting toward an obstacle during HOVER and GCS is unresponsive, what is the last-resort action?",
        "State the correct power-on sequence for the SUDARSHAN system.",
    ]))
    story.append(Spacer(1, 10))

    # ── MODULE 4 ──────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(module_banner(4, "Mission Planning"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Learning Objectives", styles["SubHeader"]))
    for obj in [
        "Construct a valid PRESET mission using bearing and distance segments.",
        "Explain the three IMUMISSION execution phases: SEG_TURN, SEG_FLY, SEG_PAUSE.",
        "Identify conditions that trigger mission abort and execute the abort procedure.",
    ]:
        story.append(Paragraph(f"• {obj}", styles["BulletText2"]))

    story.append(Paragraph("PRESET Segment Format", styles["SubHeader"]))
    story.append(Paragraph(
        "Each PRESET segment is defined by two parameters: "
        "<b>bearing</b> (0–359°, relative to current IMU heading at mission start) and "
        "<b>distance</b> (metres, 0.5–20 m). Segments are executed in order. "
        "The drone uses the complementary-filter yaw to track heading and motor differential "
        "thrust for forward movement.", styles["BodyText2"]))

    story.append(Paragraph("IMUMISSION Execution Phases", styles["SubHeader"]))
    phase_rows = [
        ["SEG_TURN",  "Drone rotates to the target bearing",
         "Yaw PID drives heading error < 3°", "Typically 1–3 s"],
        ["SEG_FLY",   "Drone translates forward at 0.4 m/s",
         "Distance estimated from integration", "Variable"],
        ["SEG_PAUSE", "Drone hovers in place for 2 s",
         "Altitude hold active", "2 s fixed"],
    ]
    story.append(build_table(
        ["Phase", "Description", "Completion Criterion", "Typical Duration"],
        phase_rows, [2.5*cm, 5.5*cm, 5*cm, 3*cm]))

    story.append(Paragraph("Abort Conditions", styles["SubHeader"]))
    for cond in [
        "sonar_ok = 0 during any flight phase → immediate LAND",
        "bat_mv ≤ 9900 mV during mission → LAND and mission abort",
        "Operator issues LAND or KILL command → mission halted, drone responds",
        "DMS timeout (30 s no GCS heartbeat) → LAND",
    ]:
        story.append(Paragraph(f"• {cond}", styles["BulletText2"]))

    story.append(Paragraph("Exercise 4 — Design a 3-Segment Square Mission", styles["ExerciseHeader"]))
    story.append(Paragraph(
        "Complete the PRESET table below to fly a 5 m square (north start, clockwise). "
        "Fill in the bearing for each segment.", styles["SmallNote"]))
    sq_rows = [
        ["1", "0°  (North)", "5 m", "SEG_TURN → SEG_FLY → SEG_PAUSE"],
        ["2", "_______",     "5 m", "SEG_TURN → SEG_FLY → SEG_PAUSE  (answer: 90°)"],
        ["3", "_______",     "5 m", "SEG_TURN → SEG_FLY → SEG_PAUSE  (answer: 180°)"],
    ]
    story.append(build_table(
        ["Seg #", "Bearing", "Distance", "Execution Phases"],
        sq_rows, [1.5*cm, 3*cm, 2.5*cm, 9*cm]))

    story.append(Paragraph("Module 4 Quiz", styles["SubHeader"]))
    story.append(quiz_table([
        "In SEG_FLY phase, how does the FC estimate distance travelled?",
        "What parameter must be set correctly at mission start for bearing references to be valid?",
        "List three conditions that cause an automatic IMUMISSION abort.",
    ]))
    story.append(Spacer(1, 10))

    # ── MODULE 5 ──────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(module_banner(5, "Maintenance & Troubleshooting"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Learning Objectives", styles["SubHeader"]))
    for obj in [
        "Perform ESC calibration and motor-ID wizard correctly.",
        "Adjust PID gains safely using the GCS tuning interface.",
        "Diagnose common faults from symptom descriptions.",
    ]:
        story.append(Paragraph(f"• {obj}", styles["BulletText2"]))

    story.append(Paragraph("ESC Calibration Procedure", styles["SubHeader"]))
    esc_steps = [
        "Remove all propellers.",
        "Power on Mega + Uno. In GCS, open PREFLIGHT → ESC_CALIB.",
        "GCS sends max-throttle signal to all ESCs simultaneously.",
        "Connect LiPo — ESCs enter calibration mode (single beep).",
        "GCS sends min-throttle — ESCs confirm calibration (descending beeps).",
        "Power-cycle ESCs; verify linear throttle response with MOTOR_TEST.",
    ]
    for i, s in enumerate(esc_steps):
        story.append(Paragraph(f"{i+1}. {s}", styles["ChecklistItem"]))

    story.append(Paragraph("Motor-ID Wizard", styles["SubHeader"]))
    story.append(Paragraph(
        "The wizard spins each motor individually at 15% throttle for 0.5 s. "
        "Observe the spinning motor and verify it matches the layout "
        "(FL=CH0, FR=CH1, RL=CH2, RR=CH3). If mismatched, update MOTOR_MAP in firmware "
        "or re-run SET_MOTOR_MAP command from GCS.", styles["BodyText2"]))

    story.append(Paragraph("PID Tuning Guidelines", styles["SubHeader"]))
    pid_rows = [
        ["Oscillation at high frequency",  "Kp too high",   "Reduce Kp by 10–15%"],
        ["Slow response, large overshoot", "Kp too low",    "Increase Kp by 10%"],
        ["Steady-state error remains",     "Ki too low",    "Increase Ki by 5%"],
        ["Integrator windup / drift",      "Ki too high",   "Reduce Ki; check for noise"],
        ["Noise / jitter on actuators",    "Kd too high",   "Reduce Kd or add D-filter"],
    ]
    story.append(build_table(
        ["Symptom", "Diagnosis", "Action"],
        pid_rows, [5.5*cm, 4*cm, 6.5*cm]))

    story.append(Paragraph("Firmware Update Procedure", styles["SubHeader"]))
    fw_steps = [
        "Disconnect Uno Pin 0/1 from Mega before flashing Uno.",
        "Use Arduino IDE with correct board/port selected.",
        "Flash Mega FC firmware first; verify READY on serial.",
        "Flash Uno motor driver firmware; verify READY.",
        "Flash ESP32 using PlatformIO; verify AP is visible.",
        "Run full PREFLIGHT test after each firmware update.",
    ]
    for i, s in enumerate(fw_steps):
        story.append(Paragraph(f"{i+1}. {s}", styles["ChecklistItem"]))

    story.append(Paragraph("Exercise 5 — Fault Identification", styles["ExerciseHeader"]))
    story.append(Paragraph(
        "Match each symptom to its most likely fault. Write the fault number in the answer column.",
        styles["SmallNote"]))
    fault_rows = [
        ["Drone spins clockwise with no yaw input",         "___", "1. Reversed motor direction / wrong prop"],
        ["IMU shows 0° roll/pitch even when tilted",        "___", "2. I2C address conflict / wiring fault"],
        ["Motors spin at unequal speeds during MOTOR_TEST", "___", "3. ESC not calibrated / motor map wrong"],
        ["GCS shows bat_mv = 0 constantly",                 "___", "4. Voltage divider missing / ADC pin float"],
        ["LAND mode never detects ground (<8 cm trigger)",  "___", "5. Sonar pointing at angle / blocked"],
    ]
    story.append(build_table(
        ["Symptom", "Answer", "Fault Library"],
        fault_rows, [6*cm, 1.5*cm, 8.5*cm]))

    story.append(Paragraph("Module 5 Quiz", styles["SubHeader"]))
    story.append(quiz_table([
        "Why must Uno Pins 0 and 1 be disconnected before flashing firmware?",
        "A pilot observes high-frequency oscillation in roll during HOVER. Which PID parameter should be reduced first?",
        "What is the purpose of the motor-ID wizard and when should it be run?",
    ]))

    # ── Certificate ───────────────────────────────────────────────────────────
    story.append(PageBreak())

    # Certificate border table
    cert_content = [
        [Paragraph("CERTIFICATE OF COMPLETION", styles["CertTitle"])],
        [Paragraph("SUDARSHAN UAV Operator Training Course", ParagraphStyle(
            "CertSub2", fontName="Helvetica-BoldOblique", fontSize=13,
            textColor=CYAN, alignment=TA_CENTER, spaceAfter=6))],
        [Spacer(1, 20)],
        [Paragraph("This certifies that", styles["CertBody"])],
        [Paragraph("_____________________________________________",
                   ParagraphStyle("CertLine", fontName="Helvetica", fontSize=14,
                                  textColor=NAVY, alignment=TA_CENTER, spaceAfter=4))],
        [Paragraph("has successfully completed all five modules of the<br/>"
                   "SUDARSHAN UAV Operator Training Course<br/>"
                   "and demonstrated competency in all assessed areas.",
                   styles["CertBody"])],
        [Spacer(1, 20)],
        [Paragraph("Date Completed: ______________________",
                   ParagraphStyle("CertDate", fontName="Helvetica", fontSize=11,
                                  textColor=DARK, alignment=TA_CENTER, spaceAfter=10))],
        [Spacer(1, 20)],
        [Paragraph("Authorized by:", ParagraphStyle("CertAuth", fontName="Helvetica-Bold",
                   fontSize=11, textColor=DARK, alignment=TA_CENTER, spaceAfter=4))],
        [Paragraph("Sudarshan<br/>Project Director, SUDARSHAN UAV Program",
                   ParagraphStyle("CertName", fontName="Helvetica-BoldOblique",
                   fontSize=13, textColor=NAVY, alignment=TA_CENTER, spaceAfter=4))],
        [Paragraph("_________________________________",
                   ParagraphStyle("CertSig", fontName="Helvetica", fontSize=11,
                   textColor=DARK, alignment=TA_CENTER))],
    ]
    cert_tbl = Table(cert_content, colWidths=[A4[0]-6*cm])
    cert_tbl.setStyle(TableStyle([
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("BOX",          (0,0), (-1,-1), 3, NAVY),
        ("INNERGRID",    (0,0), (-1,-1), 0, WHITE),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("BACKGROUND",   (0,0), (-1,-1), colors.HexColor("#f8f9ff")),
    ]))
    story.append(Spacer(1, 30))
    story.append(cert_tbl)

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"  [OK] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# PDF 3 — TROUBLESHOOTING GUIDE
# ══════════════════════════════════════════════════════════════════════════════

def build_troubleshooting():
    path = os.path.join(OUT_DIR, "SUDARSHAN_TROUBLESHOOTING_GUIDE.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=1.8*cm, rightMargin=1.8*cm,
                            topMargin=2.2*cm, bottomMargin=2.5*cm)
    styles = get_styles()
    story = []

    story.append(header_banner("SUDARSHAN UAV — TROUBLESHOOTING GUIDE",
                               "Symptom → Cause → Fix  |  Issue 1.0"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Use this guide to diagnose and resolve faults systematically. "
        "Work through the Diagnostic Steps in order before applying the Fix. "
        "Est. Time is bench repair time excluding re-flash where noted.",
        styles["BodyText2"]))
    story.append(cyan_rule())

    COL_W = [3.2*cm, 3.5*cm, 4.5*cm, 4*cm, 1.8*cm]
    HEADERS = ["Symptom", "Likely Cause", "Diagnostic Steps", "Fix", "Est. Time"]

    def ts_section(title, rows):
        story.append(section_header(title, styles))
        story.append(build_table(HEADERS, rows, COL_W))
        story.append(Spacer(1, 8))

    # Section 1 – Boot & Connectivity
    ts_section("Section 1 — Boot & Connectivity", [
        ["IMU not found on I2C scan",
         "Wrong I2C address or loose wire",
         "1. Check SDA/SCL wiring\n2. Scan I2C bus (0x68/0x69)\n3. Check AD0 pin state",
         "Re-seat connector; set AD0 LOW for 0x68; replace if dead",
         "5 min"],
        ["Motor driver (Uno) no response",
         "UART mis-wired or firmware not flashed",
         "1. Check Mega TX1 → Uno RX wiring\n2. Open Uno serial monitor\n3. Verify 'READY' message",
         "Re-wire UART; reflash Uno firmware; verify baud = 115200",
         "10 min"],
        ["Wi-Fi AP 'SUDARSHAN_AP' not visible",
         "ESP32 not powered or firmware issue",
         "1. Check 5V supply to ESP32\n2. Check TX2/RX wiring\n3. Monitor ESP32 serial",
         "Power-cycle ESP32; reflash firmware; verify AP SSID in code",
         "10 min"],
        ["GCS shows 'Connection Refused'",
         "Wrong IP/port or ESP32 not in AP mode",
         "1. Confirm IP = 192.168.4.1\n2. Confirm port = 5760\n3. Ping 192.168.4.1",
         "Update GCS config; confirm ESP32 AP mode; check firewall",
         "5 min"],
        ["ESC no startup beep",
         "No throttle signal or ESC fault",
         "1. Check ESC PWM cable\n2. Verify PCA9685 I2C\n3. Check 5V to PCA9685",
         "Re-seat PCA9685 wiring; run ESC calibration; replace ESC if silent",
         "15 min"],
    ])

    # Section 2 – Flight Instability
    ts_section("Section 2 — Flight Instability", [
        ["Roll/pitch oscillation during hover",
         "Kp too high in roll/pitch PID",
         "1. Observe frequency of oscillation\n2. Check Kp value in firmware\n3. Log PID output",
         "Reduce Kp_roll / Kp_pitch by 10–15%; re-tune Kd if needed",
         "20 min"],
        ["Lateral drift in hover",
         "IMU levelling offset or motor imbalance",
         "1. Place on level surface, check roll/pitch = ~0\n2. Run MOTOR_TEST\n3. Check prop balance",
         "Calibrate IMU level offsets; balance or replace props; check motor thrust",
         "30 min"],
        ["Yaw drift with no yaw command",
         "Motor direction / prop mismatch or IMU_YAW_SIGN wrong",
         "1. Verify CW/CCW prop placement\n2. Check yaw PID output log\n3. Review IMU_YAW_SIGN",
         "Correct prop directions; set IMU_YAW_SIGN=-1 if reversed; retune Ki_yaw",
         "15 min"],
        ["Uncontrolled altitude climb",
         "Altitude PID Kp too high or sonar noise",
         "1. Monitor alt_cm for spikes\n2. Check sonar_ok flag\n3. Review Kp_alt value",
         "Reduce Kp_alt by 10%; add sonar median filter; check sonar alignment",
         "20 min"],
        ["Motors running at uneven speeds",
         "ESC not calibrated or motor map wrong",
         "1. Run MOTOR_TEST — note uneven response\n2. Check motor map\n3. Check ESC calibration",
         "Re-run ESC calibration; verify SET_MOTOR_MAP; replace suspect ESC",
         "25 min"],
    ])

    # Section 3 – Sonar & Altitude
    ts_section("Section 3 — Sonar & Altitude", [
        ["sonar_ok = 0 reported",
         "Sonar wiring fault or out of range",
         "1. Check TRIG/ECHO wires on Mega D9/D10\n2. Test with hand at 20 cm\n3. Monitor raw echo time",
         "Re-seat sonar connector; clear any obstruction in beam path; replace sensor",
         "10 min"],
        ["alt_cm jumps suddenly to 0 or 999",
         "Sonar echo timeout / electrical noise",
         "1. Check sonar power (5V)\n2. Look for nearby motor EMI\n3. Add 100µF cap on sonar power",
         "Add decoupling capacitor; route sonar wires away from motor lines; shield cable",
         "15 min"],
        ["False landing detected mid-flight",
         "Sonar beam reflected off grass / angled surface",
         "1. Check sonar tilt angle\n2. Fly over flat surface\n3. Review consecutive-count threshold",
         "Ensure sonar is vertical; increase LAND_DETECT_COUNT in firmware",
         "10 min"],
    ])

    # Section 4 – GCS & Communication
    ts_section("Section 4 — GCS & Communication", [
        ["Telemetry display frozen",
         "TCP socket disconnect or FC loop stall",
         "1. Check GCS socket status indicator\n2. Ping ESP32\n3. Check FC serial for READY",
         "Reconnect GCS; power-cycle ESP32; check FC loop timing",
         "5 min"],
        ["Commands not reaching FC",
         "UART wiring fault or baud mismatch",
         "1. Monitor ESP32 serial — does it receive?\n2. Check Mega RX wiring\n3. Verify baud = 115200",
         "Fix ESP32→Mega wiring; verify firmware baud rates match",
         "10 min"],
        ["Web GCS shows LOCKED",
         "Another session holds priority lock",
         "1. Check if another device is connected\n2. Enter override code 1410\n3. Wait 60 s for timeout",
         "Use override code 1410; disconnect other session; power-cycle ESP32",
         "2 min"],
        ["Sequence gap warnings in GCS log",
         "UDP/TCP packet loss or FC overload",
         "1. Check Wi-Fi signal strength\n2. Monitor FC loop timing\n3. Review GCS log for pattern",
         "Move closer to AP; reduce GCS telemetry rate; check FC CPU load",
         "10 min"],
    ])

    # Section 5 – Battery & Power
    ts_section("Section 5 — Battery & Power", [
        ["bat_mv reads 0 or static",
         "Voltage divider fault or ADC pin float",
         "1. Measure battery pin with multimeter\n2. Check ADC resistor divider\n3. Check Mega pin A0",
         "Repair voltage divider; check solder joints; verify VBAT_PIN in firmware",
         "15 min"],
        ["Auto-LAND triggers at full battery",
         "VBAT_LOW threshold too high or divider ratio wrong",
         "1. Compare bat_mv to multimeter reading\n2. Check VBAT_SCALE constant\n3. Verify resistor values",
         "Recalculate and update VBAT_SCALE; verify R1/R2 divider ratio",
         "20 min"],
        ["ESCs beep continuously after power-on",
         "No valid PWM signal or ESC in error state",
         "1. Check PCA9685 outputs with oscilloscope\n2. Verify ESC power\n3. Check Uno READY status",
         "Re-run ESC calibration; reflash Uno; check PCA9685 I2C address (0x40)",
         "20 min"],
    ])

    # Section 6 – Preflight Test Failures
    ts_section("Section 6 — Preflight Test Failures", [
        ["MOTOR_TEST timeout — no motor response",
         "Uno not responding or wrong motor map",
         "1. Check Mega→Uno UART\n2. Open Uno serial monitor\n3. Verify motor map order",
         "Reflash Uno; fix UART wiring; run SET_MOTOR_MAP; re-run MOTOR_TEST",
         "15 min"],
        ["IMU preflight fail",
         "IMU not found or calibration offset too large",
         "1. Check I2C scan (expect 0x68)\n2. Place drone on level surface\n3. Review gyro drift in log",
         "Fix I2C wiring; recalibrate IMU offsets; replace MPU-6050 if unresponsive",
         "20 min"],
        ["Sonar sanity fail",
         "alt_cm outside 5–200 cm range at bench",
         "1. Check sonar wiring\n2. Place hand 30 cm from sensor\n3. Verify TRIG/ECHO pin config",
         "Fix sonar wiring; clear beam path; replace sensor if no pulse detected",
         "10 min"],
    ])

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"  [OK] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# PDF 4 — OPERATOR MANUAL
# ══════════════════════════════════════════════════════════════════════════════

def build_operator_manual():
    path = os.path.join(OUT_DIR, "SUDARSHAN_OPERATOR_MANUAL.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.2*cm, bottomMargin=2.5*cm)
    styles = get_styles()
    story = []

    story.append(header_banner("SUDARSHAN UAV — OPERATOR MANUAL",
                               "Issue 1.0  |  CONFIDENTIAL — Authorized Personnel Only"))
    story.append(Spacer(1, 8))

    # ── Table of Contents (simple) ─────────────────────────────────────────────
    story.append(section_header("Table of Contents", styles))
    toc_items = [
        ("1", "Introduction & Operating Limitations"),
        ("2", "System Description"),
        ("3", "Normal Procedures"),
        ("4", "Emergency Procedures"),
        ("5", "Systems & Indicators"),
        ("6", "Performance Data"),
    ]
    for num, title in toc_items:
        story.append(Paragraph(f"Section {num}   —   {title}", styles["BodyText2"]))
    story.append(Spacer(1, 10))
    story.append(cyan_rule())

    # ── Section 1 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("1.  Introduction & Operating Limitations", styles["ManualHeading1"]))
    story.append(Paragraph(
        "The SUDARSHAN is a custom-built quadrotor UAV designed for indoor and outdoor "
        "low-altitude research and training operations. It is operated exclusively under "
        "direct visual line-of-sight (VLOS) by trained personnel. This manual describes "
        "the procedures, limitations, and systems information required for safe and effective "
        "operation.", styles["BodyText2"]))

    story.append(Paragraph("Operating Limitations", styles["ManualHeading2"]))
    lim_rows = [
        ["Maximum Wind Speed",       "5 m/s",               "Operations shall cease above this value"],
        ["Maximum Operating Altitude","30 m AGL",            "Hard limit enforced by operator discipline"],
        ["Maximum Control Range",    "50 m (Wi-Fi range)",  "GCS signal degrades beyond 50 m line-of-sight"],
        ["Operating Temperature",    "0 °C to +40 °C",      "Battery performance degrades below 10 °C"],
        ["Maximum Payload",          "150 g",                "Exceeding payload increases instability"],
        ["Minimum Battery for Flight","10.5 V (3.5 V/cell)","Do not ARM below this voltage"],
        ["Maximum Continuous Hover", "12 min (2200 mAh)",   "Land with ≥ 2 min reserve (≈9.9 V)"],
        ["Propeller Size",           "8 × 4.5 inch",        "Replacement must match specification exactly"],
    ]
    story.append(build_table(
        ["Parameter", "Limit", "Notes"],
        lim_rows, [5*cm, 4*cm, 7*cm]))

    story.append(Paragraph("⚠  WARNING", styles["RedBold"]))
    story.append(Paragraph(
        "SUDARSHAN is not certified for operations over people, moving vehicles, or "
        "within 5 km of any aerodrome without explicit ATC authorization. The operator "
        "bears full responsibility for compliance with local UAV regulations.",
        styles["BodyText2"]))

    # ── Section 2 ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("2.  System Description", styles["ManualHeading1"]))

    story.append(Paragraph("2.1  Configuration", styles["ManualHeading2"]))
    story.append(Paragraph(
        "SUDARSHAN is an X-configuration quadrotor. Motors are designated "
        "FL (front-left), FR (front-right), RL (rear-left), RR (rear-right). "
        "FL and RR rotate clockwise (CW); FR and RL rotate counter-clockwise (CCW). "
        "Frame diagonal motor-to-motor distance: approximately 450 mm.", styles["BodyText2"]))

    story.append(Paragraph("2.2  Weight & Balance", styles["ManualHeading2"]))
    wb_rows = [
        ["Airframe (bare)",  "≈ 450 g",  "Including arms and landing gear"],
        ["Motors × 4",       "≈ 200 g",  "2212/920 KV brushless"],
        ["LiPo Battery",     "≈ 190 g",  "3S 2200 mAh 30C"],
        ["Electronics",      "≈ 120 g",  "Mega, Uno, ESP32, PCA9685, sensors"],
        ["TOTAL (no payload)","≈ 960 g", "All-up weight without payload"],
    ]
    story.append(build_table(
        ["Component", "Mass", "Notes"],
        wb_rows, [5*cm, 3*cm, 8*cm]))

    story.append(Paragraph("2.3  Electrical System", styles["ManualHeading2"]))
    story.append(Paragraph(
        "A 3S LiPo (11.1 V nominal, 12.6 V fully charged) feeds the power distribution "
        "board (PDB). Four 30A ESCs distribute power to motors. A 5 V BEC on the PDB powers "
        "the Arduino Mega, Uno, and ESP32. A dedicated voltage divider (R1=10kΩ, R2=4.7kΩ) "
        "feeds the Mega ADC for battery monitoring. The MPU-6050 IMU and PCA9685 PWM driver "
        "operate at 3.3 V from their on-board regulators.", styles["BodyText2"]))

    story.append(Paragraph("2.4  Propulsion System", styles["ManualHeading2"]))
    prop_rows = [
        ["Motor",       "Brushless 2212 / 920 KV",      "All 4 positions"],
        ["Propeller",   "8 × 4.5 inch (8045)",          "CW and CCW variants required"],
        ["ESC",         "30A with BLHeli firmware",      "All 4"],
        ["Battery",     "3S 2200 mAh LiPo, 30C",        "Single cell"],
        ["Max thrust (single)", "≈ 380 g at 100% throttle", "At 11.1 V"],
    ]
    story.append(build_table(
        ["Item", "Specification", "Notes"],
        prop_rows, [4*cm, 6*cm, 6*cm]))

    # ── Section 3 ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("3.  Normal Procedures", styles["ManualHeading1"]))

    story.append(Paragraph("3.1  Pre-Flight Checklist", styles["ManualHeading2"]))
    pf_cats = [
        ("MECHANICAL INSPECTION", [
            "All 4 propellers tight and correctly oriented (CW on FL/RR, CCW on FR/RL)",
            "Frame arms locked — no cracks, no looseness",
            "Landing gear secure",
            "Motor shafts free-spinning — no binding or grating",
            "All screws torqued — vibration check complete",
        ]),
        ("ELECTRICAL INSPECTION", [
            "LiPo cell voltages balanced (> 3.9 V/cell, < 4.2 V/cell)",
            "All ESC connectors fully seated",
            "All signal wire connectors secure",
            "No damaged or bare wiring visible",
        ]),
        ("FIRMWARE READY CHECK", [
            "Power on Mega + Uno — serial monitors show READY within 5 s",
            "Wi-Fi SSID 'SUDARSHAN_AP' visible on GCS device",
        ]),
        ("GCS PREFLIGHT TESTS", [
            "GCS connected (green indicator in title bar)",
            "MOTOR_TEST — all 4 motors spin in correct sequence (PROPS OFF)",
            "IMU_CHECK — pass (green), roll/pitch/yaw < ±2° on level surface",
            "SONAR_CHECK — pass (green), alt_cm displayed > 0",
            "bat_mv > 10 500 (≥ 3.5 V/cell) confirmed",
        ]),
        ("AREA CLEARANCE", [
            "All personnel ≥ 10 m from aircraft before ARM",
            "Wind assessed < 5 m/s",
            "Flight path clear of obstacles to planned altitude",
            "Observer designated if operating beyond 20 m",
        ]),
    ]
    for cat, items in pf_cats:
        story.append(Paragraph(cat, styles["SubHeader"]))
        for item in items:
            story.append(Paragraph(f"☐  {item}", styles["ChecklistItem"]))

    story.append(Paragraph("3.2  ESC Arming Sequence", styles["ManualHeading2"]))
    story.append(Paragraph(
        "ESCs arm automatically when the FC sends the minimum-throttle signal on power-on. "
        "The startup sequence of beeps confirms arming: one long beep = power connected; "
        "descending beeps = ESC armed. If an ESC does not beep, do NOT proceed — investigate "
        "before flight.", styles["BodyText2"]))

    story.append(Paragraph("3.3  Takeoff", styles["ManualHeading2"]))
    for step in [
        "Verify all pre-flight items checked.",
        "Ensure all personnel are ≥ 10 m clear.",
        "In GCS FLIGHT tab: issue ARM command. Confirm state = ARMED.",
        "Issue HOVER command. Drone will spin up and climb to hover altitude (~50 cm).",
        "Observe stabilization. Allow 5 s before commanding flight.",
    ]:
        story.append(Paragraph(f"• {step}", styles["BulletText2"]))

    story.append(Paragraph("3.4  Normal Flight", styles["ManualHeading2"]))
    story.append(Paragraph(
        "Monitor telemetry continuously: alt_cm, bat_mv, sonar_ok, and dms_countdown. "
        "Keep dms_countdown > 5 s by sending periodic heartbeat (GCS does this automatically "
        "when connected). Keep bat_mv > 10 500 mV for comfortable margins.", styles["BodyText2"]))

    story.append(Paragraph("3.5  Normal Landing", styles["ManualHeading2"]))
    for step in [
        "Issue LAND command from GCS FLIGHT tab.",
        "Monitor state: HOVER → LAND → auto-DISARMED.",
        "Confirm motors stop after touchdown (sonar < 8 cm × 6 counts).",
        "Disconnect LiPo within 2 minutes of landing.",
    ]:
        story.append(Paragraph(f"• {step}", styles["BulletText2"]))

    story.append(Paragraph("3.6  Post-Flight", styles["ManualHeading2"]))
    for step in [
        "Disconnect LiPo — store at 3.8 V/cell (storage charge) if not flying again within 24 h.",
        "Inspect propellers for nicks, cracks, or balance issues.",
        "Check all connectors for heat or discoloration.",
        "Log flight duration, battery condition, and any anomalies in the flight log.",
    ]:
        story.append(Paragraph(f"• {step}", styles["BulletText2"]))

    # ── Section 4 ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("4.  Emergency Procedures", styles["ManualHeading1"]))
    story.append(Paragraph(
        "All emergency procedures require immediate, decisive action. "
        "Do not hesitate. Safety of persons has absolute priority over equipment.",
        styles["BodyText2"]))

    emerg_procs = [
        ("UNCOMMANDED YAW ROTATION",
         ["Issue LAND immediately.",
          "If LAND does not take effect within 2 s, issue KILL.",
          "After landing/KILL, power-cycle drone.",
          "Root cause: wrong prop direction or IMU_YAW_SIGN. Inspect before next flight."]),
        ("ALTITUDE LOSS / UNCONTROLLED DESCENT",
         ["Issue HOVER to re-engage altitude hold.",
          "If descent continues, issue KILL immediately to prevent uncontrolled impact.",
          "Root cause: sonar_ok = 0 or altitude PID fault. Check sonar before next flight."]),
        ("GCS LOSS / TELEMETRY FREEZE",
         ["DMS will automatically issue LAND after 30 s of no heartbeat.",
          "Visually monitor drone — it should descend and land autonomously.",
          "If drone does not land within 40 s, use physical E-stop if fitted.",
          "Do NOT approach aircraft until motors have stopped for ≥ 5 s."]),
        ("BATTERY CRITICAL (bat_mv ≤ 9 900 mV)",
         ["FC automatically issues LAND — do not override.",
          "Clear landing area immediately.",
          "After landing, disconnect LiPo immediately — swollen cells are a fire hazard.",
          "Do not recharge a deeply discharged or swollen LiPo."]),
        ("MOTOR FAILURE (one motor stops)",
         ["Drone will lose control immediately — issue KILL.",
          "Clear area — drone will fall.",
          "Investigate cause: ESC fault, motor winding, prop strike.",
          "Replace ESC/motor before next flight; rebalance and test-hover at low altitude."]),
        ("KILL PROCEDURE",
         ["Issue KILL command from GCS FLIGHT tab.",
          "All motors cut immediately — drone falls.",
          "Use only when continued flight poses greater risk than fall impact.",
          "After KILL, a full power-cycle of the drone is required before re-arming."]),
    ]

    for title, steps in emerg_procs:
        story.append(Paragraph(f"■  {title}", styles["RedBold"]))
        for step in steps:
            story.append(Paragraph(f"     {step}", styles["BulletText2"]))
        story.append(Spacer(1, 4))

    # ── Section 5 ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("5.  Systems & Indicators", styles["ManualHeading1"]))

    story.append(Paragraph("5.1  Telemetry Field Definitions", styles["ManualHeading2"]))
    telem_rows = [
        ["state",          "FC flight state",           "IDLE / ARMED / HOVER / LAND / KILL / OVERRIDE"],
        ["roll_deg",       "Roll angle (°)",            "Positive = right wing down"],
        ["pitch_deg",      "Pitch angle (°)",           "Positive = nose up"],
        ["yaw_deg",        "Yaw angle (°)",             "0–360°, clockwise from north"],
        ["alt_cm",         "Sonar altitude (cm)",       "0 = ground; valid range 5–200 cm"],
        ["sonar_ok",       "Sonar validity flag",       "1 = valid; 0 = no echo / out of range"],
        ["bat_mv",         "Battery voltage (mV)",      "Full = 12 600 mV; low = 9 900 mV"],
        ["dms_countdown",  "DMS seconds remaining",     "Counts down from 30; reaches 0 → LAND"],
        ["seq",            "GCS packet sequence number","Used to detect dropped packets"],
        ["loop_ms",        "FC loop execution time (ms)","Nominal = 4 ms (250 Hz); > 6 ms = overload"],
    ]
    story.append(build_table(
        ["Field", "Description", "Range / Notes"],
        telem_rows, [3.5*cm, 5*cm, 7.5*cm]))

    story.append(Paragraph("5.2  DMS (Dead-Man Switch) Countdown", styles["ManualHeading2"]))
    story.append(Paragraph(
        "The DMS operates at three independent levels: "
        "(1) ESP32 heartbeat timer — resets on any TCP packet; "
        "(2) Mega FC internal timer — resets on any valid serial command; "
        "(3) GCS software watchdog — alerts operator if no telemetry for 5 s. "
        "If the FC timer reaches 0 (30 s), LAND is issued automatically. "
        "dms_countdown in telemetry reflects the FC-side timer.", styles["BodyText2"]))

    story.append(Paragraph("5.3  Battery State Table", styles["ManualHeading2"]))
    bat_rows = [
        ["12.6 V  (4.20 V/cell)", "100%",   "Fully charged",    "WHITE",  "Normal operations"],
        ["12.0 V  (4.00 V/cell)", "75%",    "Good",             "GREEN",  "Normal operations"],
        ["11.4 V  (3.80 V/cell)", "50%",    "Adequate",         "GREEN",  "Plan landing soon"],
        ["10.8 V  (3.60 V/cell)", "25%",    "Low",              "AMBER",  "Return and land"],
        ["10.5 V  (3.50 V/cell)", "15%",    "Very Low",         "AMBER",  "Land immediately"],
        ["9.9 V   (3.30 V/cell)", "< 5%",   "Critical",         "RED",    "Auto-LAND triggered"],
        ["< 9.9 V",               "0%",     "Over-discharged",  "RED",    "Do not recharge — inspect"],
    ]
    story.append(build_table(
        ["Voltage", "Charge %", "State", "Indicator", "Action"],
        bat_rows, [3.8*cm, 2.2*cm, 2.8*cm, 2.5*cm, 4.7*cm]))

    # ── Section 6 ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("6.  Performance Data", styles["ManualHeading1"]))

    story.append(Paragraph("6.1  Endurance", styles["ManualHeading2"]))
    story.append(Paragraph(
        "Hover endurance on a fully-charged 2200 mAh 3S LiPo is approximately "
        "8–12 minutes depending on payload and ambient conditions. "
        "Aggressive manoeuvres reduce endurance by up to 30%. "
        "Always land with a minimum of 2 minutes reserve (bat_mv ≈ 10 500 mV).",
        styles["BodyText2"]))

    story.append(Paragraph("6.2  Speed", styles["ManualHeading2"]))
    perf_rows = [
        ["Hover speed",          "0 m/s",      "Altitude-hold hover"],
        ["Slow cruise (GUIDE)",  "0.4 m/s",    "Minimum controlled translation"],
        ["Fast cruise (GUIDE)",  "2.0 m/s",    "Maximum recommended speed"],
        ["Max descent rate",     "0.5 m/s",    "LAND mode controlled descent"],
        ["Max ascent rate",      "0.8 m/s",    "HOVER to target altitude"],
    ]
    story.append(build_table(
        ["Mode", "Speed", "Notes"],
        perf_rows, [5*cm, 4*cm, 7*cm]))

    story.append(Paragraph("6.3  Altitude & Sonar Performance", styles["ManualHeading2"]))
    alt_rows = [
        ["Altitude hold accuracy",   "± 5 cm",      "In still air, smooth ground surface"],
        ["Sonar valid range",        "5 – 200 cm",  "HC-SR04 with 10° beam angle"],
        ["Sonar update rate",        "10 Hz",       "Triggered by FC loop"],
        ["Altitude response time",   "< 0.3 s",     "Step response to ± 10 cm disturbance"],
    ]
    story.append(build_table(
        ["Parameter", "Value", "Conditions"],
        alt_rows, [5.5*cm, 4*cm, 6.5*cm]))

    story.append(Paragraph("6.4  Control & PID Parameters (Default)", styles["ManualHeading2"]))
    pid_rows = [
        ["Roll",    "1.8",  "0.02", "0.6",   "250 Hz"],
        ["Pitch",   "1.8",  "0.02", "0.6",   "250 Hz"],
        ["Yaw",     "2.5",  "0.05", "0.0",   "250 Hz"],
        ["Altitude","3.0",  "0.08", "1.2",   "250 Hz"],
    ]
    story.append(build_table(
        ["Axis", "Kp", "Ki", "Kd", "Loop Rate"],
        pid_rows, [3*cm, 2*cm, 2*cm, 2*cm, 7*cm]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "End of SUDARSHAN UAV Operator Manual — Issue 1.0",
        ParagraphStyle("EndNote", fontName="Helvetica-Oblique", fontSize=9,
                       textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"  [OK] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# PDF 5 — RELEASE CHECKLIST
# ══════════════════════════════════════════════════════════════════════════════

def build_release_checklist():
    path = os.path.join(OUT_DIR, "SUDARSHAN_RELEASE_CHECKLIST.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.2*cm, bottomMargin=2.5*cm)
    styles = get_styles()
    story = []

    story.append(header_banner("SUDARSHAN UAV — RELEASE GATE CHECKLIST",
                               "Pre-Release Validation  |  Complete ALL gates before deployment"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This checklist must be completed in full before any new firmware or software version "
        "is approved for flight operations. Each item must be verified by a qualified engineer. "
        "Incomplete items constitute a release blocker.", styles["BodyText2"]))

    # Release version header
    ver_data = [
        ["Version / Tag:", "_______________", "Release Date:", "_______________"],
        ["Branch:",        "_______________", "Build SHA:",    "_______________"],
    ]
    ver_tbl = Table(ver_data, colWidths=[4*cm, 5.5*cm, 4*cm, 5.5*cm])
    ver_tbl.setStyle(TableStyle([
        ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",     (0,0), (-1,-1), 9.5),
        ("FONTNAME",     (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",     (2,0), (2,-1), "Helvetica-Bold"),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("BACKGROUND",   (0,0), (-1,-1), LGREY),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#b0bec5")),
    ]))
    story.append(ver_tbl)
    story.append(Spacer(1, 10))
    story.append(cyan_rule())

    def gate_table(gate_num, gate_name, gate_color, items):
        """Build a gate section with colour-coded header and checkbox rows."""
        # Gate header
        hdr = Paragraph(f"GATE {gate_num} — {gate_name}", ParagraphStyle(
            f"GateHdr{gate_num}", fontName="Helvetica-Bold", fontSize=12,
            textColor=WHITE, alignment=TA_LEFT))
        hdr_tbl = Table([[hdr]], colWidths=[A4[0]-4*cm])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), gate_color),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ]))
        story.append(hdr_tbl)

        # Items table
        rows = []
        for i, (item, detail) in enumerate(items):
            rows.append([
                f"☐  {i+1}.",
                item,
                detail,
                "PASS / FAIL",
                "__________"
            ])
        tbl = Table(rows, colWidths=[1.2*cm, 5.5*cm, 6*cm, 2*cm, 2.3*cm])
        style_cmds = [
            ("FONTNAME",     (0,0), (-1,-1), "Helvetica"),
            ("FONTSIZE",     (0,0), (-1,-1), 8.5),
            ("VALIGN",       (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("LEFTPADDING",  (0,0), (-1,-1), 5),
            ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#cfd8dc")),
            ("FONTNAME",     (3,0), (3,-1), "Helvetica-Bold"),
            ("TEXTCOLOR",    (3,0), (3,-1), colors.grey),
            ("FONTSIZE",     (3,0), (3,-1), 7.5),
        ]
        for i in range(0, len(rows), 2):
            style_cmds.append(("BACKGROUND", (0,i), (-1,i), LGREY))
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)
        story.append(Spacer(1, 10))

    # ── Gate 1: Code Quality ───────────────────────────────────────────────────
    gate_table(1, "Code Quality", NAVY, [
        ("pytest suite passes (0 failures)",
         "Run: pytest tests/ -v — all tests must show PASSED"),
        ("Syntax check (flake8 / pylint) clean",
         "Run: flake8 GCS/ FC/ — zero E/W errors"),
        ("No new TODO without linked issue",
         "grep -r 'TODO' — each must have #issue-number"),
        ("CHANGELOG.md updated with this release",
         "Version entry with date, changes, and breaking notes"),
        ("Version string bumped in firmware + GCS",
         "Verify VERSION constant in Mega FC and GCS config match tag"),
        ("PROTOCOL.md matches all implemented commands",
         "Manually diff command list in code vs PROTOCOL.md — no gaps"),
    ])

    # ── Gate 2: Firmware Bench Validation ─────────────────────────────────────
    gate_table(2, "Firmware Bench Validation", GREEN, [
        ("All 3 boards flashed with release firmware",
         "Mega FC, Uno motor driver, ESP32 gateway — record flash SHA"),
        ("Serial monitor shows READY on Mega + Uno",
         "Open serial at 115200; confirm within 5 s of power-on"),
        ("GCS connects and session established",
         "TCP connect to 192.168.4.1:5760; green indicator"),
        ("Telemetry flows at 10 Hz",
         "GCS log shows seq incrementing; no freezes over 30 s"),
        ("MOTOR_TEST — all 4 motors respond in order",
         "CH0 FL → CH1 FR → CH2 RL → CH3 RR; each spins 0.5 s at 15%"),
        ("ARM → HOVER nominal (props on, restrained)",
         "Drone ARM, HOVER command; confirm altitude hold; check oscillation"),
        ("LAND → auto-DISARM confirmed",
         "Issue LAND; verify state transitions HOVER→LAND→DISARMED"),
        ("DMS test: disconnect GCS for 30 s",
         "Disconnect TCP; drone must auto-LAND within 35 s; reconnect and verify"),
        ("KILL command confirmed",
         "During HOVER (restrained), issue KILL; confirm immediate motor cutoff"),
        ("Battery voltage matches multimeter",
         "Compare bat_mv to handheld multimeter reading; error < 100 mV"),
    ])

    # ── Gate 3: Security ───────────────────────────────────────────────────────
    gate_table(3, "Security Review", AMBER, [
        ("credentials.h and credentials.py NOT in staged/committed files",
         "git status; git log --name-only | grep credentials — must be empty"),
        ("No hardcoded IP addresses or credentials in source code",
         "grep -r '192\\.168\\|password\\|api_key' src/ — zero results"),
        ("AES key not logged to serial or telemetry",
         "Code review: AES key variable never passed to Serial.print or telemetry struct"),
        ("Rate limiting functional",
         "Send 20 rapid commands in 1 s; verify GCS receives RATE_LIMIT response"),
    ])

    # ── Gate 4: Documentation ──────────────────────────────────────────────────
    gate_table(4, "Documentation", CYAN, [
        ("PROTOCOL.md is current with all FC commands",
         "Compare PROTOCOL.md command table to FC command parser — no missing entries"),
        ("WIRING.md is current with actual hardware",
         "Compare WIRING.md to physical build; all pin assignments accurate"),
        ("Project report PDF regenerated for this release",
         "Run gen_report.py; verify PDF timestamp matches release date"),
        ("CHANGELOG.md has entry for this version",
         "Release section present with: version, date, changes, known issues"),
    ])

    # ── Sign-off table ─────────────────────────────────────────────────────────
    story.append(section_header("Release Sign-Off", styles))
    signoff_rows = [
        ["Bench Test & Validation", "", "________________________", "________________"],
        ["Code Review",             "", "________________________", "________________"],
        ["Release Approved By",     "Sudarshan\nProject Director", "________________________", "________________"],
    ]
    so_tbl = Table(
        [["Role", "Printed Name", "Signature", "Date"]] + signoff_rows,
        colWidths=[4.5*cm, 4.5*cm, 5*cm, 3*cm]
    )
    so_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("ALIGN",        (0,0), (-1,-1), "LEFT"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#b0bec5")),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("BACKGROUND",   (0,3), (-1,3), colors.HexColor("#fff9e6")),
        ("FONTNAME",     (1,3), (1,3), "Helvetica-BoldOblique"),
        ("TEXTCOLOR",    (1,3), (1,3), NAVY),
    ]))
    story.append(so_tbl)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "All four gates must be signed off before this version is cleared for flight operations. "
        "Any FAIL result in Gates 1–4 is a release blocker and must be resolved and re-verified.",
        ParagraphStyle("ReleaseNote", fontName="Helvetica-BoldOblique", fontSize=9,
                       textColor=RED, alignment=TA_CENTER)))

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"  [OK] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\nGenerating SUDARSHAN UAV documentation PDFs...\n")
    paths = []
    paths.append(build_quiz())
    paths.append(build_training_course())
    paths.append(build_troubleshooting())
    paths.append(build_operator_manual())
    paths.append(build_release_checklist())

    print("\nFile sizes:")
    for p in paths:
        size = os.path.getsize(p)
        print(f"  {os.path.basename(p):45s}  {size:>8,} bytes  ({size/1024:.1f} KB)")

    print("\nDone. All 5 PDFs written to:", OUT_DIR)
