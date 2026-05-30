#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           RADHA GCS — Ground Control Station v1.1           ║
║           Project  : SUDARSHAN UAV                          ║
║           Hardware : Laptop → ESP32 WiFi AP → UART          ║
║                      → Arduino Mega2560 FC → ESCs → Motors  ║
╚══════════════════════════════════════════════════════════════╝

# ════════════════════════════════════════════════════════════
# RADHA PROTOCOL v1.0
# Transport : TCP over ESP32 WiFi AP
#             Default IP : 192.168.4.1   Port : 5760
# Encoding  : UTF-8 JSON, newline-delimited (\n)
#
# ── GCS → ESP32  (Commands) ─────────────────────────────────
#   {"cmd": "ARM"}
#   {"cmd": "DISARM"}
#   {"cmd": "HOVER"}
#   {"cmd": "LAND"}
#   {"cmd": "KILL"}
#   {"cmd": "PING"}            # heartbeat — resets DMS on FC
#   {"cmd": "PRESET", "segments": [
#       {"bearing": 0.0, "dist_m": 5.0, "speed": 0.5},
#       ...
#   ]}
#   bearing : degrees clockwise from North (0–360)
#   dist_m  : metres to travel on that bearing
#   speed   : throttle factor 0.0–1.0
#
# ── ESP32 → GCS  (Telemetry @ 10 Hz) ───────────────────────
#   {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
#    "alt_cm": 0, "bat_mv": 12600,
#    "mode": "HOVER", "armed": true}
#
# ── ESP32 → GCS  (ACK) ──────────────────────────────────────
#   {"ack": "ARM",  "status": "OK"}
#   {"ack": "ARM",  "status": "ERR", "msg": "reason"}
#
# ── ESP32 → GCS  (Events) ───────────────────────────────────
#   {"info": "GCS_CONNECTED"}
#   {"info": "PHONE_CONNECTED"}
#   {"info": "PHONE_DISCONNECTED"}
#   {"dms": "FIRED", "action": "HOVER"}
# ════════════════════════════════════════════════════════════
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import threading
import json
import time
import math
import os

# ── Palette ──────────────────────────────────────────────────
BG       = "#0d0d0d"
PANEL    = "#141414"
SIDEBAR  = "#0a0a0a"
ACCENT   = "#00e5ff"
DANGER   = "#ff3b3b"
WARN     = "#ffaa00"
SUCCESS  = "#00e676"
TEXT     = "#e0e0e0"
SUBTEXT  = "#555555"

F_HEAD  = ("Consolas", 11, "bold")
F_BODY  = ("Consolas", 10)
F_SMALL = ("Consolas", 9)
F_BIG   = ("Consolas", 15, "bold")

ESP32_IP    = "192.168.4.1"
ESP32_PORT  = 5760
DMS_TIMEOUT = 30.0   # seconds before dead-man switch fires

BAT_WARN_MV = 10500  # alert threshold
BAT_CRIT_MV = 9900   # auto-land threshold (displayed in red)
LOG_MAX_LINES = 2000  # max lines in the log widget before trimming


# ─────────────────────────────────────────────────────────────
#  CONNECTION MANAGER
# ─────────────────────────────────────────────────────────────
class ConnectionManager:
    """Owns the TCP socket to the ESP32. Thread-safe send.
    Automatically reconnects on unexpected disconnection."""

    RECONNECT_DELAYS = [2, 4, 8, 16]  # seconds (exponential backoff)

    def __init__(self, on_telemetry, on_ack, on_status):
        self.on_telemetry = on_telemetry
        self.on_ack       = on_ack
        self.on_status    = on_status
        self._sock        = None
        self._running     = False
        self._lock        = threading.Lock()
        self._intentional = False   # set True when operator clicks DISCONNECT
        self._ip          = ESP32_IP
        self._port        = ESP32_PORT

    def connect(self, ip, port):
        self._ip          = ip
        self._port        = int(port)
        self._intentional = False
        self._try_connect(ip, int(port))

    def _try_connect(self, ip, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((ip, port))
            s.settimeout(None)
            self._sock    = s
            self._running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            self.on_status("CONNECTED", SUCCESS)
        except Exception as e:
            self.on_status(f"FAILED: {e}", DANGER)

    def disconnect(self):
        self._intentional = True
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.on_status("DISCONNECTED", SUBTEXT)

    def send(self, payload: dict) -> bool:
        if not self._sock:
            return False
        try:
            data = (json.dumps(payload) + "\n").encode()
            with self._lock:
                self._sock.sendall(data)
            return True
        except Exception as e:
            self.on_status(f"SEND ERR: {e}", DANGER)
            self._sock = None
            self._running = False
            return False

    def _recv_loop(self):
        buf = ""
        while self._running:
            try:
                chunk = self._sock.recv(1024).decode(errors="ignore")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pkt = json.loads(line)
                        if "ack" in pkt:
                            self.on_ack(pkt)
                        else:
                            self.on_telemetry(pkt)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                break
        self._running = False
        self.on_status("DISCONNECTED", SUBTEXT)
        # Auto-reconnect if this was not operator-initiated
        if not self._intentional:
            threading.Thread(target=self._reconnect_loop, daemon=True).start()

    def _reconnect_loop(self):
        for delay in self.RECONNECT_DELAYS:
            self.on_status(f"RECONNECTING in {delay}s…", WARN)
            time.sleep(delay)
            if self._intentional:
                return
            self.on_status(f"RECONNECTING to {self._ip}:{self._port}…", WARN)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((self._ip, self._port))
                s.settimeout(None)
                self._sock    = s
                self._running = True
                threading.Thread(target=self._recv_loop, daemon=True).start()
                self.on_status("CONNECTED", SUCCESS)
                return
            except Exception:
                pass
        self.on_status("RECONNECT FAILED — click CONNECT to retry", DANGER)

    @property
    def connected(self):
        return self._running and self._sock is not None


# ─────────────────────────────────────────────────────────────
#  DEAD-MAN SWITCH
# ─────────────────────────────────────────────────────────────
class DeadManSwitch:
    """Fires callback if reset() isn't called within timeout seconds."""

    def __init__(self, timeout, callback):
        self.timeout  = timeout
        self.callback = callback
        self._last    = time.time()
        self._active  = False

    def start(self):
        self._active = True
        self._last   = time.time()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._active = False

    def reset(self):
        self._last = time.time()

    def remaining(self):
        return max(0.0, self.timeout - (time.time() - self._last))

    def _run(self):
        while self._active:
            if time.time() - self._last > self.timeout:
                self.callback()
                self._last = time.time()
            time.sleep(1)


# ─────────────────────────────────────────────────────────────
#  FLIGHT LOG (persistent file logging)
# ─────────────────────────────────────────────────────────────
class FlightLog:
    """Writes timestamped log entries to a dated file in GCS/logs/."""

    def __init__(self):
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(log_dir, f"{ts}.log")
        self._f = open(path, "a", buffering=1)  # line-buffered
        self._f.write(f"# RADHA GCS session started {ts}\n")

    def write(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._f.write(f"[{ts}] {msg}\n")

    def write_telem(self, pkt: dict):
        ts = time.strftime("%H:%M:%S")
        self._f.write(f"[{ts}] TELEM {json.dumps(pkt)}\n")

    def close(self):
        self._f.write("# Session ended\n")
        self._f.close()


# ─────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────
class RADHAApp:

    def __init__(self, root):
        self.root = root
        self.root.title("RADHA GCS  ·  SUDARSHAN UAV")
        self.root.configure(bg=BG)
        self.root.geometry("1100x680")
        self.root.minsize(900, 580)

        self._armed       = False
        self._preset_segs = []
        self._gps_vars    = {}
        self._fix_lbl     = None
        self._bat_lbl     = None   # reference to battery value label

        self.flog = FlightLog()
        self.conn = ConnectionManager(
            on_telemetry = self._on_telem,
            on_ack       = self._on_ack,
            on_status    = self._on_conn_status,
        )
        self.dms = DeadManSwitch(DMS_TIMEOUT, self._dms_fired)

        self._build_ui()
        self._switch_tab("FLIGHT")
        self._tick()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.flog.close()
        self.root.destroy()

    # ── UI BUILD ─────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────
        top = tk.Frame(self.root, bg=SIDEBAR, height=46)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="RADHA GCS", bg=SIDEBAR, fg=ACCENT,
                 font=("Consolas", 13, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(top, text="SUDARSHAN UAV", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(side="left", pady=10)

        self._dms_lbl  = tk.Label(top, text="DMS: --s", bg=SIDEBAR,
                                   fg=SUBTEXT, font=F_SMALL)
        self._dms_lbl.pack(side="right", padx=10)

        self._conn_lbl = tk.Label(top, text="● DISCONNECTED", bg=SIDEBAR,
                                   fg=SUBTEXT, font=F_BODY)
        self._conn_lbl.pack(side="right", padx=10)

        self._mode_lbl = tk.Label(top, text="MODE: ---", bg=SIDEBAR,
                                   fg=WARN, font=F_HEAD)
        self._mode_lbl.pack(side="right", padx=14)

        self._arm_lbl  = tk.Label(top, text="DISARMED", bg=SIDEBAR,
                                   fg=DANGER, font=F_HEAD)
        self._arm_lbl.pack(side="right", padx=14)

        # ── Body ─────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        sb = tk.Frame(body, bg=SIDEBAR, width=120)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        self._tab_btns = {}
        for name in ("FLIGHT", "PRESET"):
            b = tk.Button(sb, text=name, bg=SIDEBAR, fg=SUBTEXT,
                          font=F_BODY, relief="flat", cursor="hand2",
                          activebackground=PANEL, activeforeground=ACCENT,
                          command=lambda n=name: self._switch_tab(n))
            b.pack(fill="x", padx=4, pady=2, ipady=10)
            self._tab_btns[name] = b

        # Connection widget at sidebar bottom
        cf = tk.Frame(sb, bg=SIDEBAR)
        cf.pack(side="bottom", fill="x", padx=6, pady=8)
        tk.Label(cf, text="ESP32 IP", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w")
        self._ip_var = tk.StringVar(value=ESP32_IP)
        tk.Entry(cf, textvariable=self._ip_var, bg=PANEL, fg=TEXT,
                 font=F_SMALL, insertbackground=TEXT,
                 relief="flat").pack(fill="x", pady=2)
        tk.Label(cf, text="Port", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w")
        self._port_var = tk.StringVar(value=str(ESP32_PORT))
        tk.Entry(cf, textvariable=self._port_var, bg=PANEL, fg=TEXT,
                 font=F_SMALL, insertbackground=TEXT,
                 relief="flat").pack(fill="x", pady=2)
        self._conn_btn = tk.Button(cf, text="CONNECT", bg=ACCENT, fg=BG,
                                    font=F_BODY, relief="flat", cursor="hand2",
                                    command=self._toggle_connect)
        self._conn_btn.pack(fill="x", pady=6, ipady=4)

        # Content area
        self._content = tk.Frame(body, bg=BG)
        self._content.pack(fill="both", expand=True, padx=8, pady=8)

        self._panels = {
            "FLIGHT": self._build_flight_panel(self._content),
            "PRESET": self._build_preset_panel(self._content),
        }

    def _switch_tab(self, name):
        for t, btn in self._tab_btns.items():
            btn.config(fg=ACCENT if t == name else SUBTEXT,
                       bg=PANEL  if t == name else SIDEBAR)
        for t, panel in self._panels.items():
            panel.pack(fill="both", expand=True) if t == name else panel.pack_forget()

    # ── FLIGHT PANEL ─────────────────────────────────────────

    def _build_flight_panel(self, parent):
        f = tk.Frame(parent, bg=BG)

        # Left: telemetry
        tl = tk.Frame(f, bg=PANEL)
        tl.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(tl, text="TELEMETRY", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 6))

        self._tv = {}
        rows = [
            ("ROLL",    "roll",   "°"),
            ("PITCH",   "pitch",  "°"),
            ("YAW",     "yaw",    "°"),
            ("ALT",     "alt_cm", "cm"),
            ("BATTERY", "bat_mv", "mV"),
            ("MODE",    "mode",   ""),
        ]
        g = tk.Frame(tl, bg=PANEL)
        g.pack(fill="x", padx=12)
        for i, (lbl, key, unit) in enumerate(rows):
            tk.Label(g, text=lbl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL, width=8, anchor="w").grid(row=i, column=0, pady=4)
            v = tk.StringVar(value="---")
            self._tv[key] = v
            lbl_widget = tk.Label(g, textvariable=v, bg=PANEL, fg=TEXT,
                                   font=F_BIG, anchor="w")
            lbl_widget.grid(row=i, column=1, sticky="w", padx=8)
            tk.Label(g, text=unit, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL).grid(row=i, column=2, sticky="w")
            if key == "bat_mv":
                self._bat_lbl = lbl_widget

        # Attitude indicator
        tk.Label(tl, text="ATTITUDE", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(14, 0))
        self._att = tk.Canvas(tl, bg="#111", width=190, height=190,
                               highlightthickness=0)
        self._att.pack(padx=12, pady=6)
        self._draw_ati(0, 0)

        # ── GPS / Phone data ─────────────────────────────────
        tk.Label(tl, text="GPS / PHONE", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 4))
        gg = tk.Frame(tl, bg=PANEL)
        gg.pack(fill="x", padx=12, pady=(0, 10))
        for i, (ttl, key) in enumerate([("FIX", "fix"), ("SATS", "sats"),
                ("LAT", "lat"), ("LON", "lon"), ("HEADING", "heading"),
                ("BARO", "baro_cm")]):
            tk.Label(gg, text=ttl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL, width=8, anchor="w").grid(row=i, column=0, pady=3)
            v = tk.StringVar(value="---")
            self._gps_vars[key] = v
            w = tk.Label(gg, textvariable=v, bg=PANEL, fg=TEXT,
                         font=F_BODY, anchor="w")
            w.grid(row=i, column=1, sticky="w", padx=8)
            if key == "fix":
                self._fix_lbl = w

        # Right: controls + log
        rc = tk.Frame(f, bg=PANEL, width=250)
        rc.pack(side="right", fill="y")
        rc.pack_propagate(False)

        tk.Label(rc, text="FLIGHT CONTROLS", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 6))

        for lbl, cmd, bg, fg in (
            ("ARM",    "ARM",    SUCCESS, BG),
            ("DISARM", "DISARM", WARN,    BG),
            ("HOVER",  "HOVER",  ACCENT,  BG),
            ("LAND",   "LAND",   ACCENT,  BG),
        ):
            tk.Button(rc, text=lbl, bg=bg, fg=fg, font=F_HEAD,
                      relief="flat", cursor="hand2",
                      command=lambda c=cmd: self._send_cmd(c)).pack(
                fill="x", padx=12, pady=3, ipady=10)

        tk.Frame(rc, bg=PANEL, height=8).pack()
        tk.Button(rc, text="⚠  KILL", bg=DANGER, fg="white",
                  font=("Consolas", 12, "bold"), relief="flat", cursor="hand2",
                  command=self._kill_confirm).pack(
            fill="x", padx=12, pady=3, ipady=12)

        tk.Label(rc, text="LOG", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(14, 2))
        self._log_box = tk.Text(rc, bg="#080808", fg=TEXT, font=("Consolas", 8),
                                 relief="flat", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        return f

    def _draw_ati(self, roll_deg, pitch_deg):
        c = self._att
        c.delete("all")
        cx, cy, r = 95, 95, 82
        ang    = math.radians(-roll_deg)
        pp     = pitch_deg * 1.8          # pixels per degree
        dx, dy = r * math.sin(ang), r * math.cos(ang)

        # Sky (top half relative to horizon)
        sky_pts = [
            cx - dx, cy - dy + pp,
            cx + dx, cy + dy + pp,
            cx + dx + 250, cy + dy + pp - 250,
            cx - dx - 250, cy - dy + pp - 250,
        ]
        c.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#162030", outline="")
        c.create_polygon(sky_pts, fill="#1a1a00")

        # Horizon line
        c.create_line(cx-dx, cy-dy+pp, cx+dx, cy+dy+pp,
                      fill="white", width=2)
        # Clip with a circle mask via border
        c.create_oval(cx-r, cy-r, cx+r, cy+r,
                      outline=PANEL, width=14)     # fake-clip
        c.create_oval(cx-r, cy-r, cx+r, cy+r,
                      outline=SUBTEXT, width=1)

        # Cross-hair
        c.create_line(cx-22, cy, cx-7,  cy, fill=ACCENT, width=2)
        c.create_line(cx+7,  cy, cx+22, cy, fill=ACCENT, width=2)
        c.create_rectangle(cx-3, cy-3, cx+3, cy+3, fill=ACCENT, outline="")

    # ── PRESET PANEL ─────────────────────────────────────────

    def _build_preset_panel(self, parent):
        f = tk.Frame(parent, bg=BG)

        # Left: builder
        lf = tk.Frame(f, bg=PANEL)
        lf.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(lf, text="PRESET FLIGHT PATH", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(lf, text="IMU dead-reckoning  ·  relative metre waypoints",
                 bg=PANEL, fg=SUBTEXT, font=F_SMALL).pack(anchor="w", padx=12)

        # ── Input row ────────────────────────────────────────
        ir = tk.Frame(lf, bg=PANEL)
        ir.pack(fill="x", padx=12, pady=10)

        self._e = {}
        for lbl, key, w in (
            ("Bearing °", "bearing", 6),
            ("Dist m",    "dist",    6),
            ("Speed",     "speed",   5),
        ):
            tk.Label(ir, text=lbl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL).pack(side="left", padx=(0, 2))
            e = tk.Entry(ir, bg="#1a1a1a", fg=TEXT, font=F_BODY,
                         width=w, insertbackground=TEXT, relief="flat")
            e.pack(side="left", padx=(0, 10))
            self._e[key] = e

        tk.Button(ir, text="ADD", bg=ACCENT, fg=BG, font=F_BODY,
                  relief="flat", cursor="hand2",
                  command=self._add_seg).pack(side="left", ipady=4, ipadx=10)

        # ── Segment list ─────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("R.Treeview", background="#0d0d0d", foreground=TEXT,
                        fieldbackground="#0d0d0d", font=F_BODY, rowheight=26)
        style.configure("R.Treeview.Heading", background=SIDEBAR,
                        foreground=ACCENT, font=F_SMALL)

        cols = ("#", "BEARING", "DIST (m)", "SPEED")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings",
                                   height=10, style="R.Treeview")
        for col, w in zip(cols, (40, 90, 90, 80)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")
        self._tree.pack(fill="both", expand=True, padx=12, pady=4)

        # ── Action buttons ───────────────────────────────────
        br = tk.Frame(lf, bg=PANEL)
        br.pack(fill="x", padx=12, pady=8)

        tk.Button(br, text="REMOVE SEL", bg=WARN, fg=BG,
                  font=F_SMALL, relief="flat", cursor="hand2",
                  command=self._remove_seg).pack(side="left", ipady=4, ipadx=8)
        tk.Button(br, text="CLEAR ALL", bg=DANGER, fg="white",
                  font=F_SMALL, relief="flat", cursor="hand2",
                  command=self._clear_segs).pack(side="left", padx=8,
                                                  ipady=4, ipadx=8)
        tk.Button(br, text="▶  EXECUTE PRESET", bg=SUCCESS, fg=BG,
                  font=F_HEAD, relief="flat", cursor="hand2",
                  command=self._exec_preset).pack(side="right",
                                                   ipady=6, ipadx=14)

        # Right: path preview
        rf = tk.Frame(f, bg=PANEL, width=290)
        rf.pack(side="right", fill="both")
        rf.pack_propagate(False)

        tk.Label(rf, text="PATH PREVIEW", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(10, 4))
        self._pcanvas = tk.Canvas(rf, bg="#080808", highlightthickness=0)
        self._pcanvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._pcanvas.bind("<Configure>", lambda e: self._draw_preview())

        return f

    # ── Segment helpers ──────────────────────────────────────

    def _add_seg(self):
        try:
            bearing = float(self._e["bearing"].get()) % 360
            dist    = float(self._e["dist"].get())
            speed   = round(max(0.0, min(1.0, float(self._e["speed"].get()))), 2)
        except ValueError:
            self._log("Invalid segment values", WARN)
            return

        self._preset_segs.append({"bearing": bearing, "dist_m": dist, "speed": speed})
        n = len(self._preset_segs)
        self._tree.insert("", "end", values=(n, f"{bearing:.1f}°",
                                              f"{dist:.1f}", f"{speed:.2f}"))
        for k in ("bearing", "dist", "speed"):
            self._e[k].delete(0, "end")
        self._draw_preview()

    def _remove_seg(self):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        self._tree.delete(sel[0])
        self._preset_segs.pop(idx)
        self._renumber()
        self._draw_preview()

    def _clear_segs(self):
        self._preset_segs.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._draw_preview()

    def _renumber(self):
        for i, item in enumerate(self._tree.get_children(), 1):
            v = self._tree.item(item, "values")
            self._tree.item(item, values=(i, v[1], v[2], v[3]))

    def _exec_preset(self):
        if not self._preset_segs:
            self._log("No segments defined", WARN)
            return
        if not self.conn.connected:
            self._log("Not connected", DANGER)
            return
        if not self._armed:
            self._log("Arm the drone first", WARN)
            return
        if self.conn.send({"cmd": "PRESET", "segments": self._preset_segs}):
            self._log(f"PRESET → {len(self._preset_segs)} segments sent", SUCCESS)

    # ── Path preview canvas ──────────────────────────────────

    def _draw_preview(self):
        c = self._pcanvas
        c.update_idletasks()
        W = c.winfo_width()  or 270
        H = c.winfo_height() or 420
        c.delete("all")

        # Grid
        for x in range(0, W, 30):
            c.create_line(x, 0, x, H, fill="#151515")
        for y in range(0, H, 30):
            c.create_line(0, y, W, y, fill="#151515")

        if not self._preset_segs:
            c.create_text(W//2, H//2, text="No path defined",
                          fill=SUBTEXT, font=F_SMALL)
            return

        # Build point list
        px, py = 0.0, 0.0
        pts = [(px, py)]
        for seg in self._preset_segs:
            r  = math.radians(seg["bearing"])
            px += seg["dist_m"] * math.sin(r)
            py -= seg["dist_m"] * math.cos(r)
            pts.append((px, py))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1)
        sc   = min(W, H) * 0.72 / span
        ox   = W / 2 - (sum(xs) / len(xs)) * sc
        oy   = H / 2 - (sum(ys) / len(ys)) * sc

        # Legs
        for i in range(1, len(pts)):
            x1 = pts[i-1][0]*sc + ox;  y1 = pts[i-1][1]*sc + oy
            x2 = pts[i  ][0]*sc + ox;  y2 = pts[i  ][1]*sc + oy
            c.create_line(x1, y1, x2, y2, fill=ACCENT, width=2,
                          arrow="last", arrowshape=(8, 10, 3))
            mx, my = (x1+x2)/2, (y1+y2)/2
            c.create_text(mx+6, my, anchor="w",
                          text=f"{self._preset_segs[i-1]['dist_m']:.1f}m",
                          fill=SUBTEXT, font=("Consolas", 7))

        # Waypoint dots
        for i, (wpx, wpy) in enumerate(pts):
            x = wpx*sc + ox;  y = wpy*sc + oy
            col = SUCCESS if i == 0 else (DANGER if i == len(pts)-1 else WARN)
            c.create_oval(x-5, y-5, x+5, y+5, fill=col, outline="")
            c.create_text(x+8, y, anchor="w", text=str(i),
                          fill=col, font=("Consolas", 7))

    # ── Commands ─────────────────────────────────────────────

    def _send_cmd(self, cmd: str):
        if not self.conn.connected:
            self._log("Not connected to ESP32", DANGER)
            return
        if self.conn.send({"cmd": cmd}):
            self._log(f"→ {cmd}", ACCENT)
            self.dms.reset()

    def _kill_confirm(self):
        if messagebox.askyesno("KILL MOTORS",
                               "Send KILL?\nThis cuts all motors immediately!",
                               icon="warning"):
            self._send_cmd("KILL")

    # ── Callbacks ────────────────────────────────────────────

    def _on_telem(self, pkt):
        # Handle ESP32 internal events (info, dms) before telemetry dispatch
        if "info" in pkt:
            info = pkt["info"]
            if info == "GCS_CONNECTED":
                self.root.after(0, self._log, "ESP32: GCS_CONNECTED", SUCCESS)
            elif info == "PHONE_CONNECTED":
                self.root.after(0, self._log, "ESP32: PHONE CONNECTED", SUCCESS)
            elif info == "PHONE_DISCONNECTED":
                self.root.after(0, self._log, "ESP32: PHONE DISCONNECTED", WARN)
            else:
                self.root.after(0, self._log, f"ESP32 info: {info}", SUBTEXT)
            self.flog.write(f"INFO {info}")
            return

        if "dms" in pkt:
            action = pkt.get("action", "?")
            self.root.after(0, self._log,
                            f"⚠ ESP32 DMS FIRED — {action}", DANGER)
            self.flog.write(f"DMS FIRED action={action}")
            return

        if pkt.get("type") == "phone":
            self.root.after(0, self._apply_gps, pkt)
        else:
            self.flog.write_telem(pkt)
            self.root.after(0, self._apply_telem, pkt)

    def _apply_telem(self, pkt):
        for key, var in self._tv.items():
            val = pkt.get(key, "---")
            var.set(f"{val:.1f}" if isinstance(val, float) else str(val))

        # Battery alarm coloring
        bat_mv = pkt.get("bat_mv", 0)
        if self._bat_lbl:
            if bat_mv > 0 and bat_mv < BAT_CRIT_MV:
                self._bat_lbl.config(fg=DANGER)
            elif bat_mv > 0 and bat_mv < BAT_WARN_MV:
                self._bat_lbl.config(fg=WARN)
            else:
                self._bat_lbl.config(fg=TEXT)

        # Sonar stale warning
        if pkt.get("warn") == "SONAR_STALE":
            self._log("⚠ SONAR STALE — altitude hold unreliable (drone >4m?)", WARN)

        armed = pkt.get("armed", False)
        self._armed = armed
        self._arm_lbl.config(text="ARMED" if armed else "DISARMED",
                              fg=SUCCESS if armed else DANGER)
        self._mode_lbl.config(text=f"MODE: {pkt.get('mode', '---')}")
        self._draw_ati(pkt.get("roll", 0), pkt.get("pitch", 0))

    def _apply_gps(self, pkt):
        fix = pkt.get("fix", 0)
        self._gps_vars["fix"].set("3D FIX" if fix else "NO FIX")
        if self._fix_lbl:
            self._fix_lbl.config(fg=SUCCESS if fix else DANGER)
        self._gps_vars["sats"].set(str(pkt.get("sats", 0)))
        self._gps_vars["lat"].set(f"{pkt.get('lat', 0.0):.6f}")
        self._gps_vars["lon"].set(f"{pkt.get('lon', 0.0):.6f}")
        self._gps_vars["heading"].set(f"{pkt.get('heading', 0.0):.1f}°")
        self._gps_vars["baro_cm"].set(f"{pkt.get('baro_cm', 0)} cm")

    def _on_ack(self, pkt):
        cmd, st = pkt.get("ack", "?"), pkt.get("status", "?")
        msg = pkt.get("msg", "")
        col = SUCCESS if st == "OK" else DANGER
        full = f"ACK {cmd}: {st} {msg}".strip()
        self.flog.write(full)
        self.root.after(0, self._log, full, col)

    def _on_conn_status(self, msg, col):
        self.flog.write(f"CONN {msg}")
        def _do():
            self._conn_lbl.config(text=f"● {msg}", fg=col)
            connected = "CONNECTED" in msg and "DIS" not in msg and "RECONNECT" not in msg
            self._conn_btn.config(text="DISCONNECT" if connected else "CONNECT")
            if connected:
                self.dms.start()
            elif "DISCONNECTED" in msg:
                self.dms.stop()
        self.root.after(0, _do)

    def _dms_fired(self):
        self._log("⚠ DEAD-MAN SWITCH — sending HOVER", DANGER)
        self.flog.write("DMS GCS FIRED")
        self.conn.send({"cmd": "HOVER"})

    def _toggle_connect(self):
        if self.conn.connected:
            self.conn.disconnect()
        else:
            ip   = self._ip_var.get().strip()
            port = self._port_var.get().strip()
            self._log(f"Connecting to {ip}:{port}…", SUBTEXT)
            threading.Thread(target=self.conn.connect,
                             args=(ip, port), daemon=True).start()

    # ── Tick (PING + DMS counter) ─────────────────────────────

    def _tick(self):
        if self.conn.connected:
            self.conn.send({"cmd": "PING"})
            rem = self.dms.remaining()
            self._dms_lbl.config(
                text=f"DMS: {rem:.0f}s",
                fg=DANGER if rem < 8 else (WARN if rem < 15 else SUBTEXT)
            )
        else:
            self._dms_lbl.config(text="DMS: --s", fg=SUBTEXT)
        self.root.after(1000, self._tick)

    # ── Log helper ───────────────────────────────────────────

    def _log(self, msg, color=TEXT):
        def _do():
            self._log_box.config(state="normal")
            ts  = time.strftime("%H:%M:%S")
            tag = f"c_{color.replace('#','')}"
            self._log_box.tag_config(tag, foreground=color)
            self._log_box.insert("end", f"[{ts}] {msg}\n", tag)
            self._log_box.see("end")
            # Trim oldest lines if log is too long
            line_count = int(self._log_box.index("end-1c").split(".")[0])
            if line_count > LOG_MAX_LINES:
                self._log_box.delete("1.0", f"{line_count - LOG_MAX_LINES + 200}.0")
            self._log_box.config(state="disabled")
        self.root.after(0, _do)


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app  = RADHAApp(root)
    root.mainloop()
