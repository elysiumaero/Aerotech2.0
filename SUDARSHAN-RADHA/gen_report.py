#!/usr/bin/env python3
"""Generate SUDARSHAN UAV Project Report PDF using ReportLab."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
import datetime

# ── Colour palette ────────────────────────────────────────────
NAVY   = colors.HexColor("#1a237e")
CYAN   = colors.HexColor("#00b8d4")
DARK   = colors.HexColor("#212121")
GREY   = colors.HexColor("#546e7a")
LGREY  = colors.HexColor("#eceff1")
RED    = colors.HexColor("#c62828")
GREEN  = colors.HexColor("#2e7d32")
AMBER  = colors.HexColor("#e65100")
WHITE  = colors.white
BLACK  = colors.black

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

OUT_PATH = "/home/user/Aerotech2.0/SUDARSHAN-RADHA/SUDARSHAN_PROJECT_REPORT.pdf"

# ── Styles ────────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()

    def add(name, **kw):
        if name in base.byName:
            base.byName[name].__dict__.update(ParagraphStyle(name=name, **kw).__dict__)
        else:
            base.add(ParagraphStyle(name=name, **kw))

    add("Cover_Title",
        fontSize=32, leading=38, textColor=WHITE,
        fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=8)
    add("Cover_Sub",
        fontSize=14, leading=18, textColor=CYAN,
        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4)
    add("Cover_Meta",
        fontSize=10, leading=14, textColor=colors.HexColor("#b0bec5"),
        fontName="Helvetica", alignment=TA_CENTER)

    add("H1",
        fontSize=18, leading=22, textColor=WHITE,
        fontName="Helvetica-Bold", spaceBefore=2, spaceAfter=6,
        backColor=NAVY, leftIndent=-MARGIN+5, rightIndent=-MARGIN+5,
        borderPad=6)
    add("H2",
        fontSize=13, leading=17, textColor=NAVY,
        fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4,
        borderPad=2, leftIndent=0)
    add("H3",
        fontSize=11, leading=14, textColor=GREY,
        fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=2)
    add("Body",
        fontSize=9.5, leading=14, textColor=DARK,
        fontName="Helvetica", spaceAfter=4, alignment=TA_JUSTIFY)
    add("Bullet",
        fontSize=9.5, leading=13, textColor=DARK,
        fontName="Helvetica", leftIndent=12, spaceAfter=2,
        bulletIndent=4)
    add("Code",
        fontSize=8, leading=11, textColor=colors.HexColor("#1a237e"),
        fontName="Courier", backColor=colors.HexColor("#e8eaf6"),
        leftIndent=8, rightIndent=8, spaceBefore=2, spaceAfter=2,
        borderPad=4)
    add("TableHead",
        fontSize=9, leading=11, textColor=WHITE,
        fontName="Helvetica-Bold", alignment=TA_CENTER)
    add("TableCell",
        fontSize=8.5, leading=11, textColor=DARK,
        fontName="Helvetica")
    add("TableCellCode",
        fontSize=7.5, leading=10, textColor=NAVY,
        fontName="Courier")
    add("Warn",
        fontSize=9, leading=12, textColor=RED,
        fontName="Helvetica-Bold", leftIndent=8)
    add("Note",
        fontSize=9, leading=12, textColor=colors.HexColor("#004d40"),
        fontName="Helvetica", leftIndent=8,
        backColor=colors.HexColor("#e0f2f1"), borderPad=4)
    add("TOCEntry",
        fontSize=10, leading=14, textColor=DARK, fontName="Helvetica")
    add("Footer",
        fontSize=8, textColor=GREY, fontName="Helvetica", alignment=TA_CENTER)
    add("QuickCard_Title",
        fontSize=14, leading=18, textColor=WHITE,
        fontName="Helvetica-Bold", alignment=TA_CENTER)
    return base

S = make_styles()

# ── Table helpers ─────────────────────────────────────────────
def std_table(data, col_widths, header=True):
    ts = [
        ("BACKGROUND", (0,0), (-1, 0 if header else -1), NAVY),
        ("TEXTCOLOR",  (0,0), (-1, 0 if header else -1), WHITE),
        ("FONTNAME",   (0,0), (-1, 0 if header else -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8.5),
        ("ALIGN",      (0,0), (-1,-1), "LEFT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, LGREY]),
        ("GRID",       (0,0), (-1,-1), 0.4, GREY),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("LEFTPADDING",(0,0), (-1,-1), 5),
        ("RIGHTPADDING",(0,0),(-1,-1), 5),
    ]
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    t.setStyle(TableStyle(ts))
    return t

def P(text, style="Body"):
    return Paragraph(text, S[style])

def H1(text): return P(f"  {text}", "H1")
def H2(text): return P(text, "H2")
def H3(text): return P(text, "H3")
def B(text):  return P(f"• {text}", "Bullet")
def Code(text): return P(text, "Code")
def SP(h=4):  return Spacer(1, h*mm)
def HR():     return HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=4)

# ── Cover page ────────────────────────────────────────────────
def cover_page():
    story = []
    # Dark navy background box via table trick
    cover_data = [[""]]
    cover_table = Table(cover_data, colWidths=[PAGE_W - 2*MARGIN], rowHeights=[55*mm])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    story.append(SP(10))
    story.append(cover_table)
    story.append(SP(-57))  # overlap

    story.append(Paragraph("SUDARSHAN UAV", S["Cover_Title"]))
    story.append(Paragraph("Autonomous Quadcopter — Project Report & Onboarding Guide", S["Cover_Sub"]))
    story.append(Paragraph("Version 1.2  ·  SUDARSHAN-RADHA Project", S["Cover_Meta"]))
    story.append(Paragraph(f"Generated {datetime.date.today().strftime('%d %B %Y')}", S["Cover_Meta"]))
    story.append(SP(8))

    # Callout badges
    badge_data = [["FLIGHT CONTROLLER\nArduino Mega 2560",
                   "WIFI BRIDGE\nESP32 DevKit",
                   "GROUND STATION\nPython / Web GCS",
                   "MOTOR DRIVER\nArduino Uno + PCA9685"]]
    bt = Table(badge_data, colWidths=[(PAGE_W-2*MARGIN)/4]*4, rowHeights=[14*mm])
    bt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), CYAN),
        ("TEXTCOLOR",     (0,0),(-1,-1), NAVY),
        ("FONTNAME",      (0,0),(-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 7.5),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("GRID",          (0,0),(-1,-1), 1, NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ]))
    story.append(bt)
    story.append(PageBreak())
    return story

# ── Table of contents ─────────────────────────────────────────
def toc_page():
    story = []
    story.append(H1("TABLE OF CONTENTS"))
    story.append(SP(3))
    entries = [
        ("1", "Project Overview", "3"),
        ("2", "Hardware Components", "4"),
        ("3", "System Architecture", "5"),
        ("4", "Communication Protocols", "6"),
        ("5", "Wiring Reference", "7"),
        ("6", "Flight Modes", "8"),
        ("7", "Command Protocol", "9"),
        ("8", "PID Configuration & Tuning", "11"),
        ("9", "Dead-Man Switch (3-Layer Safety)", "12"),
        ("10","Onboarding — First-Time Setup", "13"),
        ("11","Running the GCS", "15"),
        ("12","Technical Debt Audit & Fixes (v1.2)", "16"),
        ("13","Known Limitations", "19"),
        ("14","Test & Validation", "20"),
        ("15","Quick-Start Reference Card", "21"),
    ]
    toc_data = [["#", "Section", "Page"]] + entries
    cw = [10*mm, (PAGE_W-2*MARGIN)*0.78, 18*mm]
    story.append(std_table(toc_data, cw))
    story.append(PageBreak())
    return story

# ── 1. Project Overview ───────────────────────────────────────
def section_overview():
    story = []
    story.append(H1("1. PROJECT OVERVIEW"))
    story.append(SP(2))
    story.append(P(
        "SUDARSHAN UAV is an autonomous quadcopter development project. "
        "The system is built around off-the-shelf Arduino and ESP32 hardware, "
        "aiming for a self-contained flying platform with full ground-station control, "
        "dead-man safety switches, altitude hold, and mission-preset autonomous flight — "
        "all without requiring a dedicated flight-controller board."
    ))
    story.append(SP(2))
    meta = [
        ["Project Name", "SUDARSHAN UAV (RADHA Project)"],
        ["Version",      "1.2"],
        ["Branch",       "claude/repo-analysis-risk-plan-W1XlB"],
        ["Developer",    "Sudarshan"],
        ["Status",       "Active development — lab-ready, pre-flight validation pending"],
        ["GCS",          "Python/Tkinter laptop GCS  +  ESP32 Web GCS (phone browser)"],
        ["Frame",        "X-frame quadcopter, 4× brushless 1900KV motors"],
        ["Battery",      "3S LiPo  (warn: 10.5 V  |  cut-off: 9.9 V  |  full: 12.6 V)"],
        ["Control Rate", "250 Hz (Mega FC)  |  Telemetry: 10 Hz  |  GPS forward: 5 Hz"],
    ]
    t = Table(meta, colWidths=[45*mm, PAGE_W-2*MARGIN-45*mm])
    t.setStyle(TableStyle([
        ("FONTNAME",  (0,0),( 0,-1), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0),(-1,-1), 9),
        ("VALIGN",    (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",(0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[WHITE, LGREY]),
        ("GRID",      (0,0),(-1,-1), 0.3, GREY),
        ("LEFTPADDING",(0,0),(-1,-1), 6),
    ]))
    story.append(t)
    story.append(PageBreak())
    return story

# ── 2. Hardware Components ────────────────────────────────────
def section_hardware():
    story = []
    story.append(H1("2. HARDWARE COMPONENTS"))
    story.append(SP(2))
    hw = [
        ["Component",        "Part / Model",         "Role"],
        ["Flight Controller","Arduino Mega 2560",     "250 Hz control loop, 4 PID loops, 8 flight modes, UART hub"],
        ["Motor Driver",     "Arduino Uno / Nano",   "Receives 10-byte binary packets; drives PCA9685 → 4 ESCs"],
        ["WiFi Bridge",      "ESP32 DevKit (30-pin)","WiFi AP at 192.168.4.1; bridges GCS ↔ FC; web GCS server"],
        ["IMU",              "MPU6050 (I2C 0x68/69)","6-axis accel+gyro; complementary filter for roll/pitch/yaw"],
        ["Sonar",            "HC-SR04",              "Altitude measurement (25 Hz); landing detection"],
        ["PWM Driver",       "PCA9685 (I2C 0x40)",   "16-ch I2C → 4 ESC PWM signals at 50 Hz"],
        ["Motors",           "4× Brushless 1900KV",  "X-frame: FL↺ FR↻ RL↻ RR↺ (CW/CCW alternating)"],
        ["ESCs",             "4× BLHeli/SimonK-compatible","PWM 1000–1950 µs; calibrated via CAL_ESC command"],
        ["Battery",          "3S LiPo 11.1 V",       "Voltage divider on A0 (47kΩ + 10kΩ); auto-LAND at 9.9 V"],
        ["Ground Station",   "Laptop (Python 3.8+)", "Full GCS UI: telemetry, presets, preflight, nav, guide tabs"],
        ["Mobile GCS",       "Any phone browser",    "ESP32 web GCS — no laptop required; WS push at 10 Hz"],
        ["GPS",              "Phone GPS app (NMEA)", "NMEA over TCP :5762 → ESP32 → FC at 5 Hz"],
    ]
    cw = [38*mm, 42*mm, PAGE_W-2*MARGIN-80*mm]
    story.append(std_table(hw, cw))
    story.append(SP(3))
    story.append(P(
        "<b>Note on ESP32 voltage:</b> The ESP32 GPIO is 3.3 V. The Mega TX (5 V) must go through a "
        "voltage divider (e.g. 1kΩ + 2kΩ) before reaching ESP32 RX. The Mega RX can accept 3.3 V directly."
    ))
    story.append(PageBreak())
    return story

# ── 3. System Architecture ────────────────────────────────────
def section_architecture():
    story = []
    story.append(H1("3. SYSTEM ARCHITECTURE"))
    story.append(SP(2))
    story.append(P(
        "The system is a five-layer stack. Each layer has a single responsibility and communicates "
        "only with its immediate neighbours. The ESP32 is a transparent relay — it has no flight logic. "
        "The FC can land itself autonomously even if all external comms fail."
    ))
    story.append(SP(3))

    arch = [
        ["Layer", "Device", "Connects to", "Protocol"],
        ["1 — Operator UI",    "Laptop (Python GCS)\nor Phone browser", "ESP32 via WiFi",          "TCP :5760 JSON\nor WS :81"],
        ["2 — WiFi Bridge",    "ESP32",                                  "GCS (TCP)\nPhone GPS (TCP)\nMega (UART)", "TCP :5760/:5762\nUART 115200"],
        ["3 — Flight Control", "Arduino Mega 2560",                      "ESP32 (UART)\nUno (UART)\nMPU6050 (I2C)\nSonar (GPIO)", "JSON\nBinary 10-byte\nI2C\nGPIO"],
        ["4 — Motor Driver",   "Arduino Uno",                            "Mega (UART)\nPCA9685 (I2C)",   "Binary 10-byte\nI2C"],
        ["5 — Actuators",      "PCA9685 + 4 ESCs + 4 Motors",           "Uno (I2C)\nBattery",           "PWM 50 Hz"],
    ]
    cw = [38*mm, 45*mm, 50*mm, 35*mm]
    story.append(std_table(arch, cw))
    story.append(SP(4))

    story.append(H2("Data Flow Summary"))
    story.append(Code("GCS command  →  ESP32 TCP  →  Mega UART (JSON)  →  PID compute  →  Uno UART (10-byte)  →  PCA9685  →  ESC PWM"))
    story.append(Code("FC telemetry →  Mega UART  →  ESP32             →  GCS TCP / WS push (10 Hz)"))
    story.append(Code("Phone GPS    →  TCP :5762  →  ESP32 parser      →  Mega UART GPS cmd (5 Hz)"))
    story.append(SP(2))

    story.append(H2("Timing Hierarchy"))
    timing = [
        ["Rate",    "Task",                                  "Notes"],
        ["250 Hz",  "Mega control loop",                     "IMU read → complementary filter → 4× PID → motor mix → Uno packet"],
        ["~25 Hz",  "HC-SR04 sonar read",                   "pulseIn() outside 250 Hz loop (blocking up to 23 ms)"],
        ["10 Hz",   "Telemetry JSON to ESP32",               "Every 25th control-loop tick"],
        ["5 Hz",    "GPS command from ESP32 to FC",          "200 ms interval; ESP32 throttles phone data"],
        ["1 Hz",    "GCS PING heartbeat",                    "Resets DMS on both ESP32 and FC"],
        ["0.04 Hz", "Battery ADC sample",                   "Once per telemetry frame"],
    ]
    cw2 = [20*mm, 55*mm, PAGE_W-2*MARGIN-75*mm]
    story.append(std_table(timing, cw2))
    story.append(PageBreak())
    return story

# ── 4. Communication Protocols ────────────────────────────────
def section_protocols():
    story = []
    story.append(H1("4. COMMUNICATION PROTOCOLS"))
    story.append(SP(2))

    story.append(H2("4.1  GCS ↔ ESP32  (TCP :5760)"))
    story.append(P(
        "Newline-delimited UTF-8 JSON. Each message is one JSON object followed by \\n. "
        "Optional AES-128-CBC encryption: wire format is <i>base64(IV + AES_CBC(PKCS7(json))) + \\n</i>. "
        "A random 16-byte IV is prepended to every message."
    ))
    story.append(SP(2))

    story.append(H2("4.2  ESP32 ↔ Mega FC  (UART 115200)"))
    story.append(P(
        "Same newline-delimited JSON format as GCS↔ESP32. The ESP32 is a transparent relay — "
        "it forwards commands from GCS to FC and telemetry from FC to GCS without modification."
    ))
    story.append(SP(2))

    story.append(H2("4.3  Mega FC → Uno Motor Driver  (UART 115200, 250 Hz)"))
    story.append(P("10-byte binary packet, little-endian start byte, big-endian motor values:"))
    story.append(Code("[ 0xAA ] [ fl_H fl_L ] [ fr_H fr_L ] [ rl_H rl_L ] [ rr_H rr_L ] [ XOR ]"))
    story.append(P(
        "Start byte: 0xAA. Motor values: 16-bit big-endian µs (range 1000–1950). "
        "XOR checksum: XOR of bytes 1–8. Corrupt packets are silently discarded by the Uno."
    ))
    story.append(SP(2))

    story.append(H2("4.4  Telemetry JSON  (FC → GCS, 10 Hz)"))
    story.append(Code(
        '{"roll":1.2, "pitch":-0.5, "yaw":182.3, "alt_cm":45, '
        '"bat_mv":11800, "mode":"HOVER", "armed":1, "imu_ok":1, "sonar_ok":1}'
    ))
    story.append(SP(2))

    story.append(H2("4.5  GPS JSON  (ESP32 → FC, 5 Hz)"))
    story.append(Code(
        '{"cmd":"GPS", "lat":28.6139, "lon":77.2090, "alt":215.0, '
        '"heading":182.3, "baro_cm":21500, "fix":1, "sats":8}'
    ))
    story.append(SP(2))

    story.append(H2("4.6  WebSocket  (ESP32 port 81 → Phone Browser)"))
    story.append(P(
        "ESP32 pushes merged telemetry+GPS JSON over WebSocket at FC rate (~10 Hz). "
        "The phone browser uses WS as primary channel and falls back to HTTP GET /api/telem "
        "(1 s poll) if WS disconnects. Auto-reconnect every 3 s."
    ))
    story.append(PageBreak())
    return story

# ── 5. Wiring Reference ───────────────────────────────────────
def section_wiring():
    story = []
    story.append(H1("5. WIRING REFERENCE"))
    story.append(SP(2))

    story.append(H2("5.1  Mega 2560 Pin Assignments"))
    mega_wiring = [
        ["Mega Pin", "Signal",       "Connected To",                    "Notes"],
        ["Pin 18 (TX1)", "UART TX → ESP32", "ESP32 GPIO16 (RX2) via divider", "5V→3.3V: 1kΩ+2kΩ divider"],
        ["Pin 19 (RX1)", "UART RX ← ESP32", "ESP32 GPIO17 (TX2)",             "3.3V direct — Mega RX tolerates it"],
        ["Pin 16 (TX2)", "Motor packet TX",  "Uno Pin 0 (RX)",                 "115200 baud; disconnect when flashing Uno"],
        ["Pin 17 (RX2)", "Motor ready RX",   "Uno Pin 1 (TX)",                 "Uno sends 'READY' after ESC arming"],
        ["Pin 20 (SDA)", "I2C SDA",          "MPU6050 SDA",                    "4.7kΩ pull-up to 3.3V"],
        ["Pin 21 (SCL)", "I2C SCL",          "MPU6050 SCL",                    "4.7kΩ pull-up to 3.3V"],
        ["Pin 7",        "Sonar TRIG",       "HC-SR04 TRIG",                   "5V GPIO output"],
        ["Pin 8",        "Sonar ECHO",       "HC-SR04 ECHO via divider",       "5V→3.3V needed if using 3.3V Mega"],
        ["A0",           "Battery ADC",      "LiPo + via 47kΩ+10kΩ",          "Scale: 5000/1023 × 5.7"],
        ["GND",          "Common ground",    "ESP32 GND, Uno GND, sensors",    "CRITICAL — must be common"],
    ]
    cw = [28*mm, 28*mm, 50*mm, PAGE_W-2*MARGIN-106*mm]
    story.append(std_table(mega_wiring, cw))
    story.append(SP(3))

    story.append(H2("5.2  Uno / PCA9685 / ESC Connections"))
    uno_wiring = [
        ["Uno Pin", "Signal",        "Connected To",     "Notes"],
        ["Pin 0 (RX)", "Packet RX",  "Mega Pin 16 (TX2)","⚠ Disconnect when flashing via USB"],
        ["Pin 1 (TX)", "Ready TX",   "Mega Pin 17 (RX2)","⚠ Disconnect when flashing via USB"],
        ["A4 (SDA)",   "I2C SDA",    "PCA9685 SDA",      "Address 0x40 default"],
        ["A5 (SCL)",   "I2C SCL",    "PCA9685 SCL",      ""],
        ["5V",         "PCA9685 VCC","PCA9685 VCC pin",  ""],
        ["GND",        "Common GND", "PCA9685 GND",      ""],
    ]
    story.append(std_table(uno_wiring, cw))
    story.append(SP(3))

    story.append(H2("5.3  PCA9685 ESC Channel Mapping"))
    esc_map = [
        ["PCA9685 Channel", "Motor Position", "Rotation",         "Mix sign (roll/pitch/yaw)"],
        ["CH 0",            "Front-Left  (FL)", "Clockwise ↺",    "+pitch  +roll  −yaw"],
        ["CH 1",            "Front-Right (FR)", "Counter-CW ↻",   "+pitch  −roll  +yaw"],
        ["CH 2",            "Rear-Left   (RL)", "Counter-CW ↻",   "−pitch  +roll  +yaw"],
        ["CH 3",            "Rear-Right  (RR)", "Clockwise ↺",    "−pitch  −roll  −yaw"],
    ]
    cw2 = [35*mm, 40*mm, 35*mm, PAGE_W-2*MARGIN-110*mm]
    story.append(std_table(esc_map, cw2))
    story.append(SP(2))
    story.append(P(
        "<b>Motor layout (top view X-frame):</b>  FL(↺) — FR(↻) diagonally opposite. "
        "Props: CW motors use CW props, CCW motors use CCW props."
    ))
    story.append(PageBreak())
    return story

# ── 6. Flight Modes ───────────────────────────────────────────
def section_modes():
    story = []
    story.append(H1("6. FLIGHT MODES"))
    story.append(SP(2))
    modes = [
        ["Mode",        "Value", "Description",                                              "Entry / Exit"],
        ["DISARMED",    "0",     "Motors off. Safe state.",                                  "Boot default; DISARM cmd; landing detect"],
        ["HOVER",       "1",     "Level hold + altitude hold. Roll/pitch/yaw setpoints zeroed.","ARM cmd (→HOVER); HOVER cmd from any mode"],
        ["LAND",        "2",     "Slow descent at 12 cm/s. Auto-disarm at alt < 8 cm (×6).", "LAND cmd; battery critical; FAILSAFE"],
        ["RTL",         "3",     "⚠ NOT IMPLEMENTED — falls back to LAND immediately.",      "RTL cmd (→LAND)"],
        ["OVERRIDE",    "4",     "Direct roll/pitch/yaw/throttle setpoints from GCS.",       "OVERRIDE cmd with roll/pitch/yaw/thr"],
        ["FAILSAFE",    "5",     "Same as LAND. Triggered by 30 s DMS timeout.",             "FC DMS fires after 30 s silence"],
        ["KILL",        "6",     "Instant motor cut. No recovery — must power-cycle.",        "KILL cmd (double-tap on web GCS)"],
        ["IMUMISSION",  "7",     "IMU-only autonomous preset path execution.",                "PRESET cmd with segments[]"],
    ]
    cw = [28*mm, 14*mm, 75*mm, PAGE_W-2*MARGIN-117*mm]
    story.append(std_table(modes, cw))
    story.append(SP(3))

    story.append(H2("State Machine Summary"))
    story.append(Code(
        "DISARMED ──ARM──► HOVER ──LAND──► LAND ──landing detect──► DISARMED\n"
        "         ◄DISARM─       ──OVERRIDE─► OVERRIDE\n"
        "                        ──PRESET──► IMUMISSION ──complete──► HOVER\n"
        "                        ──KILL────► KILL\n"
        "         ◄──────────────────────── (30s DMS) ──► FAILSAFE ──► LAND"
    ))
    story.append(PageBreak())
    return story

# ── 7. Command Protocol ───────────────────────────────────────
def section_commands():
    story = []
    story.append(H1("7. COMMAND PROTOCOL"))
    story.append(SP(2))
    story.append(P(
        "All commands are sent as JSON objects with a <b>cmd</b> key, terminated by \\n. "
        "The FC responds with an ACK JSON: <b>{\"ack\":\"CMD\", \"status\":\"OK\"}</b> or "
        "<b>{\"ack\":\"CMD\", \"status\":\"ERR\", \"msg\":\"reason\"}</b>."
    ))
    story.append(SP(3))

    cmds = [
        ["Command",       "JSON Payload",                                               "Armed?", "Description"],
        ["ARM",           '{"cmd":"ARM"}',                                              "No",     "Arm ESCs (2.5 s), save home GPS, reset PIDs → HOVER"],
        ["FORCE_ARM",     '{"cmd":"FORCE_ARM"}',                                        "No",     "ARM bypassing IMU check (admin only)"],
        ["DISARM",        '{"cmd":"DISARM"}',                                           "Any",    "Immediate motor cut → DISARMED"],
        ["HOVER",         '{"cmd":"HOVER"}',                                            "Yes",    "Reset setpoints, hold current altitude"],
        ["LAND",          '{"cmd":"LAND"}',                                             "Yes",    "Slow descent, auto-disarm at ground"],
        ["KILL",          '{"cmd":"KILL"}',                                             "Yes",    "Emergency motor cut (no recovery)"],
        ["PING",          '{"cmd":"PING"}',                                             "Any",    "DMS heartbeat — no response"],
        ["OVERRIDE",      '{"cmd":"OVERRIDE","roll":5,"pitch":-3,\n"yaw":0,"throttle":1180}', "Yes", "Direct attitude + throttle setpoints"],
        ["ALT_HOLD",      '{"cmd":"ALT_HOLD","alt_cm":150}',                            "Yes",    "Update altitude PID target (30–500 cm)"],
        ["PRESET",        '{"cmd":"PRESET","segments":[{"bearing":0,\n"dist_m":5,"speed":0.5}]}', "Yes", "Upload & execute up to 16 waypoint segments"],
        ["MOTOR_TEST",    '{"cmd":"MOTOR_TEST","motor":"FL",\n"throttle":1100,"duration_ms":1500}', "No", "Spin one motor for bench test (props off!)"],
        ["SPIN_CH",       '{"cmd":"SPIN_CH","ch":0,"thr":1100,"dur":2000}',             "No",     "Spin raw PCA9685 channel (motor-ID wizard)"],
        ["SET_MOTOR_MAP", '{"cmd":"SET_MOTOR_MAP","fl":2,"fr":0,\n"rl":3,"rr":1}',     "No",     "Save channel→motor mapping from wizard"],
        ["CAL_ESC",       '{"cmd":"CAL_ESC"}',                                          "No",     "ESC throttle range calibration (props off!)"],
        ["GPS",           '{"cmd":"GPS","lat":28.6,"lon":77.2,\n"fix":1,"sats":8,...}', "Any",    "Inject GPS data from ESP32"],
    ]
    cw = [30*mm, 62*mm, 16*mm, PAGE_W-2*MARGIN-108*mm]
    story.append(std_table(cmds, cw))
    story.append(SP(2))
    story.append(P(
        "<b>Web GCS priority lock:</b> When the Python laptop GCS is connected on TCP :5760, "
        "the ESP32 blocks all web GCS commands (returns <i>{ok:0, locked:1}</i>). "
        "Override codes: <b>1410</b> (session unlock) or <b>980752</b> (master — unlocks everything)."
    ))
    story.append(PageBreak())
    return story

# ── 8. PID Configuration ──────────────────────────────────────
def section_pid():
    story = []
    story.append(H1("8. PID CONFIGURATION & TUNING"))
    story.append(SP(2))

    pid_params = [
        ["Axis",      "Kp",   "Ki",   "Kd",   "Output Limit",  "Notes"],
        ["Roll",      "1.8",  "0.05", "0.80", "±300 µs",       "Negative = left bank. Flip sign if drone rolls wrong way."],
        ["Pitch",     "1.8",  "0.05", "0.80", "±300 µs",       "Negative = nose down."],
        ["Yaw",       "2.0",  "0.02", "0.00", "±120 µs",       "Kd=0: gyro noise would saturate derivative on yaw."],
        ["Altitude",  "3.0",  "0.10", "1.50", "±250 µs",       "Integrator frozen when sonar is stale (v1.2 fix)."],
    ]
    cw = [22*mm, 14*mm, 14*mm, 14*mm, 22*mm, PAGE_W-2*MARGIN-86*mm]
    story.append(std_table(pid_params, cw))
    story.append(SP(3))

    story.append(H2("Tuning Guide (Ziegler-Nichols-lite for beginners)"))
    steps = [
        "Set Ki=0, Kd=0. Increase Kp until the drone oscillates at hover (Ku).",
        "Set Kp = 0.6 × Ku as starting point.",
        "Add Kd slowly until oscillations damp within 1–2 cycles.",
        "Add Ki slowly to correct steady-state altitude/heading error.",
        "For yaw: leave Kd=0; gyro noise is too high for derivative.",
        "Re-tune after changing props, battery, or payload weight.",
    ]
    for i, s in enumerate(steps, 1):
        story.append(B(f"Step {i}: {s}"))
    story.append(SP(2))
    story.append(P(
        "<b>IMU yaw sign:</b> If the drone spins the wrong direction on first flight, "
        "change <b>IMU_YAW_SIGN</b> from 1 to -1 in SUDARSHAN_FC.ino. "
        "Do this on the bench, NOT in the air."
    ))
    story.append(SP(2))
    story.append(P(
        "<b>Complementary filter:</b> CF_ALPHA=0.98 is tuned for 250 Hz. "
        "The Mega caps loop dt at 10 ms to prevent gyro spikes. "
        "If the drone rocks at ~1 Hz during hover, increase CF_ALPHA slightly (0.985)."
    ))
    story.append(PageBreak())
    return story

# ── 9. Dead-Man Switch ────────────────────────────────────────
def section_dms():
    story = []
    story.append(H1("9. DEAD-MAN SWITCH — 3-LAYER SAFETY"))
    story.append(SP(2))
    story.append(P(
        "Three independent watchdogs ensure the drone enters a safe state even if GCS software crashes, "
        "WiFi drops, or the ESP32 locks up. Each layer acts independently."
    ))
    story.append(SP(3))

    dms = [
        ["Layer", "Lives In",   "Timeout",  "Trigger Condition",               "Action",       "Backup For"],
        ["1 — GCS DMS",   "Python GCS\n(laptop)",     "30 s",  "Operator idle — no button/slider moved", "Sends HOVER cmd → ESP32",    "Operator inattention"],
        ["2 — ESP32 DMS", "ESP32\nfirmware",           "30 s",  "No GCS TCP packet received",             "Injects HOVER directly into FC UART", "GCS crash / WiFi drop"],
        ["3 — FC DMS",    "Mega 2560\nfirmware",       "30 s",  "No UART command received",               "Mode → FAILSAFE → LAND → DISARM", "All comms fail"],
    ]
    cw = [28*mm, 28*mm, 17*mm, 52*mm, 42*mm, PAGE_W-2*MARGIN-167*mm]
    story.append(std_table(dms, cw))
    story.append(SP(3))

    story.append(H2("DMS Reset Path"))
    story.append(Code(
        "Operator clicks/moves GCS  →  GCS sends PING every 25 s (+ every command)\n"
        "PING → ESP32 lastPing reset → FC lastCmdMs reset\n"
        "Web GCS: JS sends PING every 25 s via POST /api/cmd while tab is open"
    ))
    story.append(SP(2))
    story.append(P(
        "<b>Web-only operation (no laptop):</b> The ESP32 DMS stays disarmed until a TCP GCS connects. "
        "The FC DMS is always active. The web GCS JavaScript sends a PING every 25 s automatically, "
        "keeping the FC DMS alive as long as the phone browser tab is open."
    ))
    story.append(PageBreak())
    return story

# ── 10. Onboarding — First-Time Setup ────────────────────────
def section_onboarding():
    story = []
    story.append(H1("10. ONBOARDING — FIRST-TIME SETUP"))
    story.append(SP(2))

    story.append(H2("10.1  Required Libraries (Arduino IDE)"))
    libs = [
        ["Library",                     "Install via",          "Used By"],
        ["ArduinoJson v6",              "Library Manager",      "Mega FC, ESP32"],
        ["Adafruit PWM Servo Driver",   "Library Manager",      "Uno motor driver"],
        ["WebSockets (Markus Sattler)", "Library Manager",      "ESP32 bridge"],
        ["Wire.h",                      "Built-in",             "All boards"],
    ]
    cw = [60*mm, 45*mm, PAGE_W-2*MARGIN-105*mm]
    story.append(std_table(libs, cw))
    story.append(SP(3))

    story.append(H2("10.2  Flashing Sequence"))
    flash_steps = [
        ("Flash Uno first", "Open SUDARSHAN_MOTOR_UNO.ino. Disconnect wires from Pin 0 and Pin 1. "
         "Select Board: Arduino Uno. Upload. Reconnect wires after flashing."),
        ("Flash Mega FC", "Open SUDARSHAN_FC.ino. Select Board: Arduino Mega 2560, Port: COMx/ttyUSBx. Upload."),
        ("Configure ESP32 credentials", "Copy credentials.h.example to credentials.h. "
         "Edit WIFI_SSID, WIFI_PASS, and optionally AES_KEY. "
         "The SSID is the AP the ESP32 broadcasts — default SUDARSHAN_AP / radha2026."),
        ("Flash ESP32", "Open ATLAS_ESP32_Bridge_v2.ino in Arduino IDE. "
         "Select Board: ESP32 Dev Module. Select correct port. Upload."),
        ("Python GCS setup", "cd SUDARSHAN-RADHA/GCS/  then  pip install cryptography. "
         "Copy credentials.py from template. Set ENCRYPT_ENABLED=True if using AES."),
        ("Power-on sequence", "Power Mega+Uno first (wait for ESC arming beeps ~3 s). "
         "Then power ESP32. Connect phone/laptop to WiFi SUDARSHAN_AP. "
         "Run: python3 radha_gcs.py"),
    ]
    for i, (title, body) in enumerate(flash_steps, 1):
        story.append(KeepTogether([
            P(f"<b>Step {i}: {title}</b>", "H3"),
            P(body),
            SP(1),
        ]))
    story.append(SP(2))

    story.append(H2("10.3  Common Boot Messages (USB Serial Monitor)"))
    story.append(Code(
        "══ SUDARSHAN FC v1.0 ══\n"
        "[UNO ] waiting for motor driver (ESC arming ~3s)...\n"
        "[UNO ] motor driver ready — ESCs armed\n"
        "[IMU ] MPU6050 OK at 0x68\n"
        "[IMU ] Calibrating — keep still...\n"
        "[IMU ] Offsets: 0.123 / -0.045 / 0.891\n"
        "[SONAR] 45.2 cm\n"
        "[PID ] initialized\n"
        "[READY] DISARMED — waiting for GCS"
    ))
    story.append(SP(2))
    story.append(P(
        "<b>If IMU not found:</b> Check SDA→Pin20, SCL→Pin21, VCC→3.3V, GND common. "
        "ARM will be blocked until MPU6050 is detected."
    ))
    story.append(PageBreak())
    return story

# ── 11. Running the GCS ───────────────────────────────────────
def section_gcs():
    story = []
    story.append(H1("11. RUNNING THE GCS"))
    story.append(SP(2))

    story.append(H2("11.1  Python Laptop GCS"))
    steps = [
        "Connect laptop to WiFi: <b>SUDARSHAN_AP</b> (password: radha2026)",
        "Run: <b>python3 radha_gcs.py</b>",
        "Login dialog appears — enter credentials from auth.json",
        "Click <b>CONNECT</b> — status bar turns green on success",
        "Run <b>PREFLIGHT</b> tab tests (IMU, sonar, motor direction — props OFF)",
        "Once critical tests pass, ARM button unlocks",
        "Optionally click <b>INAUGURATE</b> for ceremonial T-minus countdown",
        "Click <b>ARM</b> → drone enters HOVER mode",
        "Monitor telemetry panel: roll/pitch/yaw/altitude/battery",
        "Use PRESET tab to build and execute autonomous paths",
    ]
    for s in steps:
        story.append(B(s))
    story.append(SP(3))

    story.append(H2("11.2  Phone Web GCS (no laptop)"))
    steps2 = [
        "Connect phone to WiFi: <b>SUDARSHAN_AP</b>",
        "Open browser → navigate to <b>http://192.168.4.1/</b>",
        "GCS page loads — telemetry shows '---' until Mega is powered",
        "Tap <b>START GPS</b> → grant location permission → GPS streams automatically",
        "Tap <b>ARM</b> → enter priority code if laptop GCS is also connected",
        "KILL button: tap once (turns red/armed), tap again within 3 s → KILL sent",
        "DMS countdown visible in status bar — resets on every command",
    ]
    for s in steps2:
        story.append(B(s))
    story.append(SP(3))

    story.append(H2("11.3  GCS Tabs (Python)"))
    tabs = [
        ["Tab",       "Purpose"],
        ["FLIGHT",    "Manual control: ARM/DISARM/HOVER/LAND/KILL, OVERRIDE sliders, ALT setpoint"],
        ["PRESET",    "Build autonomous paths: bearing+distance segments; click-mode canvas input"],
        ["PREFLIGHT", "Hardware validation: IMU, sonar, motor direction tests (requires DISARMED)"],
        ["NAV",       "Navigation compass: target lat/lon → bearing+distance → FLY TO preset"],
        ["GUIDE",     "Training checklist + SIM LOCK (blocks ARM in simulation context)"],
    ]
    story.append(std_table(tabs, [25*mm, PAGE_W-2*MARGIN-25*mm]))
    story.append(PageBreak())
    return story

# ── 12. Technical Debt Audit & Fixes ─────────────────────────
def section_debt():
    story = []
    story.append(H1("12. TECHNICAL DEBT AUDIT & FIXES (v1.2)"))
    story.append(SP(2))
    story.append(P(
        "A full technical debt audit was performed against all four firmware/software files. "
        "The table below lists every finding. Items marked <b>FIXED</b> were resolved in the v1.2 "
        "commit on branch <i>claude/repo-analysis-risk-plan-W1XlB</i>."
    ))
    story.append(SP(3))

    issues = [
        ["#",  "Sev",      "Component",  "Issue",                                      "Status"],
        ["1",  "CRITICAL", "FC",         "Sonar EMA cold-start: alt=0 on ARM causes immediate descent",  "FIXED"],
        ["2",  "CRITICAL", "FC",         "Motor mix asymmetric saturation: loses attitude authority",     "FIXED"],
        ["3",  "CRITICAL", "Uno",        "UART packet desync: no timeout — stuck mid-packet forever",    "FIXED"],
        ["4",  "CRITICAL", "FC",         "PRESET div-by-zero if dist_m=0 in segment",                    "FIXED"],
        ["5",  "CRITICAL", "FC",         "UART receive buffer: String heap grows without bound on bad packets", "FIXED"],
        ["6",  "HIGH",     "ESP32",      "DMS race: KILL/LAND overridden by coincident DMS fire at T=30s","FIXED"],
        ["7",  "HIGH",     "ESP32",      "AES malloc failure silently transmits plaintext",               "FIXED"],
        ["8",  "HIGH",     "FC",         "GPS compass correction unbounded: stale GPS yanks heading",     "FIXED"],
        ["9",  "HIGH",     "Python GCS", "Seq gap false-positive: ESP32 reboot floods log, loses real warnings","FIXED"],
        ["10", "MEDIUM",   "FC",         "Gyro spike (I2C glitch) saturates PID integrator",             "FIXED"],
        ["11", "MEDIUM",   "FC",         "Altitude PID wind-up when sonar is stale",                     "FIXED"],
        ["12", "MEDIUM",   "FC",         "SET_MOTOR_MAP accepted mid-flight: violent asymmetric thrust",  "FIXED"],
        ["13", "MEDIUM",   "Python GCS", "Preflight motor test ACK race: bad motor reports PASS",        "FIXED"],
        ["14", "MEDIUM",   "Python GCS", "NAV FLY TO sends unrecognised JSON to FC — silently ignored",  "FIXED"],
        ["15", "LOW",      "FC",         "RTL is dead code — falls back to LAND without GPS",             "OPEN (hardware)"],
        ["16", "LOW",      "FC",         "CF filter tuned for 250 Hz; slower loops shift alpha",          "OPEN (hardware)"],
        ["17", "LOW",      "ESP32",      "TCP client/server mode doc ambiguity for GPS app",              "OPEN (docs)"],
        ["18", "LOW",      "All",        "No boot handshake/version sync between boards",                 "OPEN"],
        ["19", "LOW",      "Python GCS", "Flight log timestamps not synchronised with FC millis()",       "OPEN"],
        ["20", "LOW",      "ESP32",      "Passwords hardcoded in firmware (physical access = bypass)",    "OPEN (by design)"],
    ]

    def sev_color(row):
        if row[1] == "CRITICAL": return RED
        if row[1] == "HIGH":     return AMBER
        if row[1] == "MEDIUM":   return colors.HexColor("#1565c0")
        return GREY

    cw = [10*mm, 20*mm, 24*mm, 95*mm, 20*mm]
    t_data = [issues[0]] + issues[1:]
    t = Table(t_data, colWidths=cw, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0,0), (-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ALIGN",         (0,0), (-1,-1), "LEFT"),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("GRID",          (0,0), (-1,-1), 0.3, GREY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
    ]
    # Colour severity column
    for r, row in enumerate(issues[1:], 1):
        c = sev_color(row)
        style_cmds.append(("TEXTCOLOR", (1,r),(1,r), c))
        style_cmds.append(("FONTNAME",  (1,r),(1,r), "Helvetica-Bold"))
    # Green FIXED, orange OPEN
    for r, row in enumerate(issues[1:], 1):
        if row[4] == "FIXED":
            style_cmds.append(("TEXTCOLOR", (4,r),(4,r), GREEN))
            style_cmds.append(("FONTNAME",  (4,r),(4,r), "Helvetica-Bold"))
        else:
            style_cmds.append(("TEXTCOLOR", (4,r),(4,r), AMBER))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(PageBreak())
    return story

# ── 13. Known Limitations ─────────────────────────────────────
def section_limits():
    story = []
    story.append(H1("13. KNOWN LIMITATIONS"))
    story.append(SP(2))

    limits = [
        ("RTL Not Implemented",
         "Return-to-Launch requires a dedicated GPS module on the Mega. Currently MODE_RTL "
         "immediately falls back to LAND in place. The web GCS and Python GCS expose an RTL button "
         "but the operator will see an ERR ACK and the drone will land where it is."),
        ("IMU-Only Navigation",
         "PRESET missions use gyro heading and sonar altitude. There is no position hold. "
         "Wind and prop wash will cause the drone to drift off the intended path. Outdoor use "
         "without GPS requires calm conditions."),
        ("Sonar Range & Reliability",
         "HC-SR04 has a practical range of ~2–3 m. Readings become unreliable above 2 m, "
         "in very dusty/humid conditions, or when the drone tilts beyond ~30°. "
         "The 'sonar stale' flag guards against this but altitude hold is lost."),
        ("No Position Hold",
         "Without GPS, the drone has no way to hold a GPS position. HOVER holds attitude "
         "(level) and altitude (sonar), but it will drift laterally in any wind."),
        ("Single-Axis Battery Voltage",
         "Battery voltage is read from a single analog pin via a resistor divider. "
         "The divider ratio assumes a 3S pack. Using a different cell count without "
         "updating BATT_SCALE will report incorrect voltage and may trigger premature LAND."),
        ("WiFi AP Only",
         "The ESP32 runs as an Access Point only. There is no station-mode fallback. "
         "If interference prevents WiFi connection, the only option is to power-cycle the ESP32."),
        ("Uno Upload Requires Wire Disconnect",
         "Pins 0 and 1 on the Uno are shared between UART (motor packets) and the USB-to-Serial "
         "chip. The wires from the Mega must be physically disconnected every time the Uno sketch "
         "is updated."),
    ]
    for title, body in limits:
        story.append(KeepTogether([
            H3(f"⚠  {title}"),
            P(body),
            SP(1),
        ]))
    story.append(PageBreak())
    return story

# ── 14. Test & Validation ─────────────────────────────────────
def section_testing():
    story = []
    story.append(H1("14. TEST & VALIDATION"))
    story.append(SP(2))

    story.append(H2("14.1  Python Unit Tests"))
    story.append(P("Run from SUDARSHAN-RADHA/GCS/:"))
    story.append(Code("pip install pytest\npytest tests/ -v"))
    tests = [
        ["Test File",                     "Coverage"],
        ["test_protocol_parsing.py",      "Telemetry JSON routing, ACK parsing, info events, seq gap detection"],
        ["test_connection_manager.py",    "TCP send/recv, JSON framing, DMS timeout, reconnect"],
        ["test_dms.py",                   "Dead-man switch timer accuracy, reset logic, fire action"],
    ]
    story.append(std_table(tests, [55*mm, PAGE_W-2*MARGIN-55*mm]))
    story.append(SP(3))

    story.append(H2("14.2  Bench Test Procedure"))
    story.append(P("Full procedure in SUDARSHAN-RADHA/TEST/BENCH_TEST.md. Summary:"))
    bench = [
        ["Test",                 "Expected Result",                    "Safe?"],
        ["ESP32 boot",           "AP SUDARSHAN_AP visible in WiFi scan","Yes"],
        ["GCS TCP connect",      "Status bar green, telemetry flowing", "Yes"],
        ["MPU6050 detection",    "[IMU] OK at 0x68 in serial monitor",  "Yes"],
        ["Sonar sanity",         "alt_cm ~25–40 cm when on bench",      "Yes"],
        ["Battery voltage",      "bat_mv within 200 mV of multimeter",  "Yes"],
        ["MOTOR_TEST FL",        "FL motor spins briefly (props OFF!)", "Props off"],
        ["MOTOR_TEST all",       "All 4 motors confirmed spinning",     "Props off"],
        ["Motor direction",      "Verify CW/CCW per wiring diagram",    "Props off"],
        ["Phone GPS streaming",  "lat/lon update in GCS GPS panel",     "Yes"],
        ["ARM → HOVER",          "Drone level, altitude holds",         "Tethered"],
        ["DMS timeout",          "HOVER/FAILSAFE after 30s silence",    "Tethered"],
        ["KILL command",         "Motors cut instantly",                 "Tethered"],
    ]
    cw = [45*mm, 75*mm, 25*mm]
    story.append(std_table(bench, cw))
    story.append(SP(3))

    story.append(H2("14.3  Pre-Flight Checklist (Outdoor)"))
    story.append(P("Full checklist in SUDARSHAN-RADHA/TEST/Pre-Flight Checklist.md"))
    preflight = [
        "Battery charged (≥ 11.5 V), securely mounted",
        "All motor screws tight, props correct direction (CW/CCW)",
        "Props balanced and free of cracks",
        "All wires routed away from props",
        "ESC calibration confirmed (CAL_ESC run once on new ESCs)",
        "Motor map verified (SET_MOTOR_MAP wizard run after any rewiring)",
        "GCS connected, telemetry nominal, sonar reading correct altitude",
        "IMU calibration: placed level, motionless during boot",
        "Preflight tab: all critical tests PASS",
        "Phone GPS fix acquired (≥ 6 satellites recommended)",
        "Area clear of people and obstacles within 10 m radius",
        "Arm only after verbal 'CLEAR' call to bystanders",
    ]
    for item in preflight:
        story.append(B(f"☐  {item}"))
    story.append(PageBreak())
    return story

# ── 15. Quick-Start Card ──────────────────────────────────────
def section_quickstart():
    story = []
    story.append(H1("15. QUICK-START REFERENCE CARD"))
    story.append(SP(2))

    # Left column: laptop GCS, Right column: phone GCS
    left = [
        P("<b>LAPTOP GCS</b>", "H2"),
        SP(1),
        Code("cd SUDARSHAN-RADHA/GCS/\npython3 radha_gcs.py"),
        SP(1),
        P("WiFi: <b>SUDARSHAN_AP</b>  /  radha2026"),
        P("IP: <b>192.168.4.1</b>  |  TCP :5760"),
        SP(1),
        P("<b>Startup sequence:</b>"),
        B("Power Mega+Uno (wait 3 s ESC beeps)"),
        B("Power ESP32"),
        B("Connect WiFi, run python3 radha_gcs.py"),
        B("Login → Connect → Preflight tab"),
        B("All critical tests PASS → ARM unlocks"),
        B("ARM → HOVER → Fly"),
        SP(2),
        P("<b>Emergency:</b>"),
        B("KILL button (double-tap on phone)"),
        B("DISARM button on laptop"),
        B("Kill WiFi → FC DMS fires in 30 s → LAND"),
    ]
    right = [
        P("<b>PHONE WEB GCS</b>", "H2"),
        SP(1),
        Code("http://192.168.4.1/"),
        SP(1),
        P("No laptop needed. Works on any browser."),
        SP(1),
        P("<b>Controls:</b>"),
        B("ARM / DISARM / HOVER / LAND"),
        B("KILL: tap once (red) → tap again in 3 s"),
        B("ALT▼: altitude setpoint slider"),
        B("PATH▼: tap waypoints on canvas"),
        B("NAV▼: fly to GPS coordinate"),
        B("START GPS: stream phone location"),
        SP(2),
        P("<b>Priority lock:</b>"),
        B("If laptop GCS connected → web blocked"),
        B("Enter <b>1410</b> to override (session)"),
        B("Enter <b>980752</b> to override (master)"),
    ]

    card = Table(
        [[left, right]],
        colWidths=[(PAGE_W-2*MARGIN)/2 - 3*mm, (PAGE_W-2*MARGIN)/2 - 3*mm]
    )
    card.setStyle(TableStyle([
        ("VALIGN",   (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("LINEAFTER", (0,0),(0,-1), 0.5, GREY),
    ]))
    story.append(card)
    story.append(SP(4))
    story.append(HR())

    # ESC range table
    story.append(H3("ESC Throttle Range"))
    esc = [
        ["Signal",    "µs",   "Meaning"],
        ["ESC_ARM",   "1000", "Arming pulse — motors off, ESC armed"],
        ["ESC_MIN",   "1050", "Minimum running throttle"],
        ["ESC_IDLE",  "1150", "Hover baseline — tune for your AUW"],
        ["ESC_MAX",   "1950", "Maximum throttle"],
    ]
    story.append(std_table(esc, [35*mm, 20*mm, PAGE_W-2*MARGIN-55*mm]))
    story.append(SP(2))
    story.append(HR())

    # Battery reference
    story.append(H3("3S LiPo Reference"))
    bat = [
        ["Condition",     "Voltage",  "Action"],
        ["Full charge",   "12.6 V",   "Normal operation"],
        ["Nominal hover", "11.1 V",   "Normal operation"],
        ["WARN threshold","10.5 V",   "Land soon — telemetry flag set"],
        ["CRIT threshold","9.9 V",    "Auto-LAND triggered immediately"],
        ["Storage",       "11.4 V",   "Ideal for long-term storage"],
    ]
    story.append(std_table(bat, [45*mm, 25*mm, PAGE_W-2*MARGIN-70*mm]))
    return story

# ── Page header/footer ────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(WHITE)
    canvas.drawString(MARGIN, h - 9*mm, "SUDARSHAN UAV — Project Report v1.2")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(CYAN)
    canvas.drawRightString(w - MARGIN, h - 9*mm, "CONFIDENTIAL — SUDARSHAN-RADHA PROJECT")
    # Footer
    canvas.setFillColor(GREY)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawCentredString(w/2, 8*mm, f"Page {doc.page}  ·  Generated {datetime.date.today()}")
    canvas.restoreState()

def on_cover(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 20*mm, w, 20*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0d1a4a"))
    canvas.rect(0, 0, w, 28*mm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#546e7a"))
    canvas.drawCentredString(w/2, 10*mm, f"SUDARSHAN UAV  ·  RADHA Project  ·  {datetime.date.today()}")
    canvas.restoreState()

# ── Build document ────────────────────────────────────────────
def build_pdf():
    doc = SimpleDocTemplate(
        OUT_PATH,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18*mm,
        bottomMargin=16*mm,
        title="SUDARSHAN UAV — Project Report v1.2",
        author="Sudarshan / RADHA Project",
        subject="Quadcopter UAV — Architecture, Onboarding & Technical Reference",
    )

    story = []
    story += cover_page()
    story += toc_page()
    story += section_overview()
    story += section_hardware()
    story += section_architecture()
    story += section_protocols()
    story += section_wiring()
    story += section_modes()
    story += section_commands()
    story += section_pid()
    story += section_dms()
    story += section_onboarding()
    story += section_gcs()
    story += section_debt()
    story += section_limits()
    story += section_testing()
    story += section_quickstart()

    doc.build(story,
              onFirstPage=on_cover,
              onLaterPages=on_page)
    print(f"PDF written: {OUT_PATH}")

if __name__ == "__main__":
    build_pdf()
