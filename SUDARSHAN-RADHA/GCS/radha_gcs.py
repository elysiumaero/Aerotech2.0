#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           RADHA GCS — Ground Control Station v1.2           ║
║           Project  : SUDARSHAN UAV                          ║
╚══════════════════════════════════════════════════════════════╝
New in v1.2:
  • Login panel with SHA-256 hashed credentials
  • Inauguration mode — T-minus ceremonial countdown
  • Hardware preflight tests with MOTOR_TEST command
  • AES-128-CBC encrypted connection (toggle in credentials.py)
  • ARM interlock until critical preflight tests pass
  • Telemetry sequence-gap detection
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import threading
import json
import time
import math
import os
import sys
import hashlib
import base64
import secrets
import ssl
import ipaddress
import datetime
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Optional AES dependency ───────────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as _crypto_pad
    _AES_AVAILABLE = True
except BaseException:  # catches ImportError and broken-extension panics (pyo3 PanicException)
    _AES_AVAILABLE = False

# ── Load local credentials (not in git) ───────────────────────
try:
    sys.path.insert(0, os.path.dirname(__file__))
    import credentials as _creds
    AES_KEY         = getattr(_creds, "AES_KEY", "your32hexcharkey0000000000000000")
    ENCRYPT_ENABLED = getattr(_creds, "ENCRYPT_ENABLED", False) and _AES_AVAILABLE
except ImportError:
    AES_KEY         = "your32hexcharkey0000000000000000"
    ENCRYPT_ENABLED = False

AUTH_FILE    = os.path.join(os.path.dirname(__file__), "auth.json")
GPS_TLS_CERT = os.path.join(os.path.dirname(__file__), "gcs_tls_cert.pem")
GPS_TLS_KEY  = os.path.join(os.path.dirname(__file__), "gcs_tls_key.pem")
GPS_HTTPS_PORT = 8443

# ── GPS HTTPS page (served over TLS so navigator.geolocation works) ─────────
# Identical layout to the ESP32 HTTP fallback page; same JS paths (/gps, /status).
_GPS_PAGE_HTML = """\
<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0d0d0d">
<title>SUDARSHAN GPS</title>
<style>
body{background:#0d0d0d;color:#e0e0e0;font-family:monospace;padding:24px;text-align:center;margin:0}
h2{color:#00e5ff;margin:0 0 20px}
.val{font-size:1.3em;color:#00e676;margin:6px 0}
.err{color:#ff3b3b}.ok{color:#00e676}.dim{color:#555}.note{font-size:.8em;color:#555;margin-top:8px}
button{background:#00e5ff;color:#000;border:none;padding:14px 28px;
       border-radius:4px;font-size:1em;cursor:pointer;margin-top:18px;
       -webkit-tap-highlight-color:transparent}
#gcs{font-size:0.85em;margin-top:14px}
</style>
</head>
<body>
<h2>SUDARSHAN GPS LINK</h2>
<div id="st" class="dim">Tap START to stream GPS to drone</div>
<div class="val" id="lat">LAT: &#8212;</div>
<div class="val" id="lon">LON: &#8212;</div>
<div class="val" id="acc">ACC: &#8212;</div>
<div class="val" id="hdg">HDG: &#8212;</div>
<div id="gcs" class="dim">GCS: checking&#8230;</div>
<button onclick="go()">&#9654; START GPS</button>
<div class="note">Served securely via GCS laptop &mdash; all browsers supported</div>
<script>
function go(){
  if(!navigator.geolocation){
    document.getElementById('st').innerHTML='<span class="err">Geolocation not supported</span>';return;
  }
  document.getElementById('st').textContent='Requesting GPS…';
  navigator.geolocation.watchPosition(function(p){
    var c=p.coords;
    document.getElementById('lat').textContent='LAT: '+c.latitude.toFixed(6);
    document.getElementById('lon').textContent='LON: '+c.longitude.toFixed(6);
    document.getElementById('acc').textContent='ACC: '+c.accuracy.toFixed(0)+'m';
    document.getElementById('hdg').textContent='HDG: '+(c.heading!=null?c.heading.toFixed(1)+'\xb0':'N/A');
    document.getElementById('st').innerHTML='<span class="ok">● GPS STREAMING</span>';
    fetch('/gps',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lat:c.latitude,lon:c.longitude,
        alt:c.altitude||0,heading:c.heading||0,acc:c.accuracy})
    }).catch(function(){});
  },function(e){
    document.getElementById('st').innerHTML='<span class="err">'+(e.message||'GPS error')+'</span>';
  },{enableHighAccuracy:true,maximumAge:0,timeout:10000});
}
setInterval(function(){
  fetch('/status').then(function(r){return r.json();}).then(function(d){
    document.getElementById('gcs').innerHTML=
      d.gcs?'<span class="ok">● GCS CONNECTED</span>':
            '<span class="dim">GCS: not connected</span>';
  }).catch(function(){});
},3000);
</script>
</body></html>
"""

# ── TLS certificate helpers ───────────────────────────────────────────────────

def _detect_ap_ip():
    """Return the laptop's IP on the SUDARSHAN_AP network (192.168.4.x), or None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.4.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip if ip.startswith("192.168.4.") else None
    except Exception:
        return None

def _ensure_tls_cert():
    """Generate a self-signed cert valid for all 192.168.4.1–5 IPs (10-year)."""
    if os.path.exists(GPS_TLS_CERT) and os.path.exists(GPS_TLS_KEY):
        return True

    san_ips = [f"192.168.4.{i}" for i in range(1, 6)]

    # Try cryptography library (already a dep for AES)
    try:
        from cryptography import x509 as _x509
        from cryptography.x509.oid import NameOID as _OID
        from cryptography.hazmat.primitives import hashes as _H, serialization as _S
        from cryptography.hazmat.primitives.asymmetric import ec as _EC

        key  = _EC.generate_private_key(_EC.SECP256R1())
        subj = _x509.Name([_x509.NameAttribute(_OID.COMMON_NAME, "SUDARSHAN UAV")])
        ip_sans = [_x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ips]
        cert = (
            _x509.CertificateBuilder()
            .subject_name(subj).issuer_name(subj)
            .public_key(key.public_key())
            .serial_number(_x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(_x509.SubjectAlternativeName(ip_sans), critical=False)
            .sign(key, _H.SHA256())
        )
        with open(GPS_TLS_CERT, "wb") as f:
            f.write(cert.public_bytes(_S.Encoding.PEM))
        with open(GPS_TLS_KEY, "wb") as f:
            f.write(key.private_bytes(_S.Encoding.PEM,
                                      _S.PrivateFormat.PKCS8,
                                      _S.NoEncryption()))
        return True
    except BaseException:
        pass

    # Fall back to subprocess openssl (Linux/macOS/WSL)
    try:
        sans_str = ",".join(f"IP:{ip}" for ip in san_ips)
        subprocess.run([
            "openssl", "req", "-x509", "-nodes",
            "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
            "-keyout", GPS_TLS_KEY,
            "-out",    GPS_TLS_CERT,
            "-days",   "3650",
            "-subj",   "/CN=SUDARSHAN UAV",
            "-addext",  f"subjectAltName={sans_str}",
        ], check=True, capture_output=True)
        return True
    except Exception:
        pass

    return False


class GpsHttpsServer:
    """HTTPS GPS page server — lets any phone browser stream GPS to the drone.

    The phone connects to https://[laptop-ip]:8443/, taps START, grants location
    permission, and GPS flows: phone → GCS (here) → ESP32 TCP → FC UART.
    HTTPS is required because browsers block navigator.geolocation on plain HTTP.
    The self-signed cert will trigger a one-time browser warning; tap
    'Advanced → Proceed' and it's remembered for the site.
    """

    def __init__(self):
        self._server  = None
        self.url      = None
        self._gps_cb  = None

    def set_gps_callback(self, cb):
        self._gps_cb = cb

    def start(self, log_fn=None):
        if not _ensure_tls_cert():
            if log_fn:
                log_fn("GPS HTTPS: cert generation failed (need openssl or cryptography lib)", WARN)
            return None

        _gps_cb = lambda d: self._gps_cb(d) if self._gps_cb else None
        _port   = GPS_HTTPS_PORT

        class _H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    body = _GPS_PAGE_HTML.encode()
                    self.send_response(200)
                    self.send_header("Content-Type",   "text/html; charset=utf-8")
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/status":
                    body = b'{"gcs":1}'
                    self.send_response(200)
                    self.send_header("Content-Type",   "application/json")
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/gps":
                    try:
                        n    = int(self.headers.get("Content-Length", 0))
                        data = json.loads(self.rfile.read(n))
                        _gps_cb(data)
                        body = b'{"ok":1}'
                        self.send_response(200)
                        self.send_header("Content-Type",   "application/json")
                        self.send_header("Content-Length", len(body))
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception:
                        self.send_response(400)
                        self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *_):
                pass  # Suppress HTTP access log

        try:
            # Bind to 0.0.0.0 so the server starts regardless of whether the
            # laptop is already connected to SUDARSHAN_AP.  The cert covers
            # 192.168.4.1–5, so whatever IP the laptop gets on the AP subnet
            # will be accepted by the phone's browser.
            srv = HTTPServer(("0.0.0.0", _port), _H)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(GPS_TLS_CERT, GPS_TLS_KEY)
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
            self._server = srv
            threading.Thread(target=srv.serve_forever, daemon=True).start()

            # Best-effort URL display — detect AP IP if already connected
            ap_ip     = _detect_ap_ip() or "192.168.4.2"
            self.url  = f"https://{ap_ip}:{_port}/"
            return self.url
        except Exception as e:
            if log_fn:
                log_fn(f"GPS HTTPS server failed: {e}", WARN)
            return None

    def stop(self):
        if self._server:
            self._server.shutdown()


# ── Palette ───────────────────────────────────────────────────
BG      = "#0d0d0d"
PANEL   = "#141414"
SIDEBAR = "#0a0a0a"
ACCENT  = "#00e5ff"
DANGER  = "#ff3b3b"
WARN    = "#ffaa00"
SUCCESS = "#00e676"
GOLD    = "#ffd700"
TEXT    = "#e0e0e0"
SUBTEXT = "#555555"

F_HEAD  = ("Consolas", 11, "bold")
F_BODY  = ("Consolas", 10)
F_SMALL = ("Consolas",  9)
F_BIG   = ("Consolas", 15, "bold")
F_HUGE  = ("Consolas", 48, "bold")

ESP32_IP      = "192.168.4.1"
ESP32_PORT    = 5760
DMS_TIMEOUT   = 30.0
BAT_WARN_MV   = 10500
BAT_CRIT_MV   = 9900
LOG_MAX_LINES = 2000

# ─────────────────────────────────────────────────────────────
#  CRYPTO LAYER
# ─────────────────────────────────────────────────────────────
class CryptoLayer:
    """AES-128-CBC encrypt/decrypt. Disabled gracefully if not available."""

    def __init__(self, key_hex: str, enabled: bool):
        self._enabled = enabled and _AES_AVAILABLE
        if self._enabled:
            self._key = bytes.fromhex(key_hex)   # 16 bytes for AES-128

    def encrypt(self, plaintext: str) -> bytes:
        if not self._enabled:
            return (plaintext + "\n").encode()
        iv  = secrets.token_bytes(16)
        pad = _crypto_pad.PKCS7(128).padder()
        padded = pad.update(plaintext.encode()) + pad.finalize()
        enc = Cipher(algorithms.AES(self._key), modes.CBC(iv)).encryptor()
        ct  = enc.update(padded) + enc.finalize()
        return (base64.b64encode(iv + ct).decode() + "\n").encode()

    def decrypt(self, line: str) -> str:
        if not self._enabled:
            return line.strip()
        try:
            raw = base64.b64decode(line.strip())
            iv, ct = raw[:16], raw[16:]
            dec = Cipher(algorithms.AES(self._key), modes.CBC(iv)).decryptor()
            padded = dec.update(ct) + dec.finalize()
            unpad  = _crypto_pad.PKCS7(128).unpadder()
            return (unpad.update(padded) + unpad.finalize()).decode()
        except Exception:
            return line.strip()   # fall back to raw on decode error


# ─────────────────────────────────────────────────────────────
#  LOGIN DIALOG
# ─────────────────────────────────────────────────────────────
class LoginDialog:
    """Modal login / create-account dialog. Returns True if authenticated."""

    def __init__(self, master):
        self.result   = False
        self._auth    = self._load()
        self._root    = master

        self._win = tk.Toplevel(master)
        self._win.title("RADHA GCS — Login")
        self._win.configure(bg=BG)
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._cancel)

        # Centre on screen
        self._win.update_idletasks()
        w, h = 340, 260
        sx = (self._win.winfo_screenwidth()  - w) // 2
        sy = (self._win.winfo_screenheight() - h) // 2
        self._win.geometry(f"{w}x{h}+{sx}+{sy}")

        tk.Label(self._win, text="RADHA GCS", bg=BG, fg=ACCENT,
                 font=("Consolas", 18, "bold")).pack(pady=(22, 2))
        tk.Label(self._win, text="SUDARSHAN UAV", bg=BG, fg=SUBTEXT,
                 font=F_SMALL).pack()

        frm = tk.Frame(self._win, bg=BG)
        frm.pack(pady=18)

        tk.Label(frm, text="Username", bg=BG, fg=TEXT, font=F_BODY,
                 width=10, anchor="w").grid(row=0, column=0, padx=6, pady=6)
        self._user = tk.Entry(frm, bg=PANEL, fg=TEXT, font=F_BODY,
                              insertbackground=TEXT, relief="flat", width=18)
        self._user.grid(row=0, column=1, pady=6)

        tk.Label(frm, text="Password", bg=BG, fg=TEXT, font=F_BODY,
                 width=10, anchor="w").grid(row=1, column=0, padx=6, pady=6)
        self._pass = tk.Entry(frm, bg=PANEL, fg=TEXT, font=F_BODY,
                              insertbackground=TEXT, relief="flat", width=18,
                              show="●")
        self._pass.grid(row=1, column=1, pady=6)
        self._pass.bind("<Return>", lambda _: self._submit())

        self._msg = tk.Label(self._win, text="", bg=BG, fg=DANGER, font=F_SMALL)
        self._msg.pack()

        if self._auth is None:
            lbl = "CREATE ACCOUNT"
            action = self._create
        else:
            lbl = "LOGIN"
            action = self._submit

        tk.Button(self._win, text=lbl, bg=ACCENT, fg=BG, font=F_HEAD,
                  relief="flat", cursor="hand2", command=action).pack(
            ipadx=24, ipady=6, pady=4)

        self._user.focus()
        self._win.grab_set()
        master.wait_window(self._win)

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _hash(pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    def _load(self):
        if not os.path.exists(AUTH_FILE):
            return None
        with open(AUTH_FILE) as f:
            return json.load(f)

    def _save(self, username: str, pw: str):
        with open(AUTH_FILE, "w") as f:
            json.dump({"username": username,
                       "password_hash": self._hash(pw)}, f)

    def _submit(self):
        u = self._user.get().strip()
        p = self._pass.get()
        if not self._auth:
            self._msg.config(text="No account found — create one first.")
            return
        if u == self._auth["username"] and \
                self._hash(p) == self._auth["password_hash"]:
            self.result = True
            self._win.destroy()
        else:
            self._msg.config(text="Invalid username or password.")
            self._pass.delete(0, "end")

    def _create(self):
        u = self._user.get().strip()
        p = self._pass.get()
        if len(u) < 2:
            self._msg.config(text="Username must be at least 2 characters.")
            return
        if len(p) < 4:
            self._msg.config(text="Password must be at least 4 characters.")
            return
        self._save(u, p)
        self.result = True
        self._win.destroy()

    def _cancel(self):
        self.result = False
        self._win.destroy()


# ─────────────────────────────────────────────────────────────
#  CONNECTION MANAGER
# ─────────────────────────────────────────────────────────────
class ConnectionManager:
    RECONNECT_DELAYS = [2, 4, 8, 16]

    def __init__(self, on_telemetry, on_ack, on_status, crypto: CryptoLayer = None):
        self.on_telemetry = on_telemetry
        self.on_ack       = on_ack
        self.on_status    = on_status
        self._crypto      = crypto
        self._sock        = None
        self._running     = False
        self._lock        = threading.Lock()
        self._intentional = False
        self._ip          = ESP32_IP
        self._port        = ESP32_PORT

    def connect(self, ip, port):
        self._ip, self._port = ip, int(port)
        self._intentional    = False
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
        self._running     = False
        if self._sock:
            try: self._sock.close()
            except Exception: pass
            self._sock = None
        self.on_status("DISCONNECTED", SUBTEXT)

    def send(self, payload: dict) -> bool:
        if not self._sock:
            return False
        try:
            raw  = json.dumps(payload)
            data = self._crypto.encrypt(raw) if self._crypto else (raw + "\n").encode()
            with self._lock:
                self._sock.sendall(data)
            return True
        except Exception as e:
            self.on_status(f"SEND ERR: {e}", DANGER)
            self._sock    = None
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
                    line = self._crypto.decrypt(line) if self._crypto else line
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
#  FLIGHT LOG
# ─────────────────────────────────────────────────────────────
class FlightLog:
    def __init__(self):
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")
        self._f = open(path, "a", buffering=1)
        self._f.write(f"# RADHA GCS session started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    def write(self, msg):
        self._f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def write_telem(self, pkt):
        self._f.write(f"[{time.strftime('%H:%M:%S')}] TELEM {json.dumps(pkt)}\n")

    def close(self):
        self._f.write("# Session ended\n")
        self._f.close()


# ─────────────────────────────────────────────────────────────
#  INAUGURATION DIALOG
# ─────────────────────────────────────────────────────────────
class InaugurationDialog:
    """T-minus ceremonial countdown then ARM + initial hover."""

    def __init__(self, master, send_cmd, log):
        self._send    = send_cmd
        self._log     = log
        self._running = False

        self._win = tk.Toplevel(master)
        self._win.title("INAUGURATION")
        self._win.configure(bg="#000")
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._abort)

        w, h = 480, 400
        sx = (self._win.winfo_screenwidth()  - w) // 2
        sy = (self._win.winfo_screenheight() - h) // 2
        self._win.geometry(f"{w}x{h}+{sx}+{sy}")

        tk.Label(self._win, text="SUDARSHAN UAV", bg="#000", fg=GOLD,
                 font=("Consolas", 14, "bold")).pack(pady=(20, 2))

        frm = tk.Frame(self._win, bg="#000")
        frm.pack(pady=8)
        tk.Label(frm, text="Mission Name:", bg="#000", fg=TEXT,
                 font=F_BODY).grid(row=0, column=0, padx=8, pady=4, sticky="e")
        self._name_var = tk.StringVar(value="INAUGURAL FLIGHT")
        tk.Entry(frm, textvariable=self._name_var, bg=PANEL, fg=GOLD,
                 font=F_BODY, relief="flat", width=22,
                 insertbackground=GOLD).grid(row=0, column=1, pady=4)

        tk.Label(frm, text="T-minus (s):", bg="#000", fg=TEXT,
                 font=F_BODY).grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self._t_var = tk.StringVar(value="10")
        tk.Entry(frm, textvariable=self._t_var, bg=PANEL, fg=GOLD,
                 font=F_BODY, relief="flat", width=6,
                 insertbackground=GOLD).grid(row=1, column=1, sticky="w", pady=4)

        # Countdown display
        self._cd_var = tk.StringVar(value="T")
        tk.Label(self._win, textvariable=self._cd_var, bg="#000", fg=GOLD,
                 font=F_HUGE).pack(pady=10)

        self._status_var = tk.StringVar(value="Configure and press INITIATE")
        tk.Label(self._win, textvariable=self._status_var, bg="#000", fg=TEXT,
                 font=F_BODY, wraplength=440).pack(pady=4)

        btn_frm = tk.Frame(self._win, bg="#000")
        btn_frm.pack(pady=14)
        self._start_btn = tk.Button(btn_frm, text="▶  INITIATE SEQUENCE",
                                     bg=GOLD, fg="#000", font=F_HEAD,
                                     relief="flat", cursor="hand2",
                                     command=self._start)
        self._start_btn.pack(side="left", ipadx=16, ipady=8, padx=8)
        tk.Button(btn_frm, text="✕  ABORT", bg=DANGER, fg="white",
                  font=F_HEAD, relief="flat", cursor="hand2",
                  command=self._abort).pack(side="left", ipadx=16, ipady=8, padx=8)

    def _start(self):
        try:
            t = int(self._t_var.get())
            assert 3 <= t <= 60
        except Exception:
            self._status_var.set("T-minus must be 3–60 seconds.")
            return
        self._running = True
        self._start_btn.config(state="disabled")
        name = self._name_var.get().strip() or "INAUGURAL FLIGHT"
        self._log(f"INAUGURATION: {name} — T-minus {t}s", GOLD)
        threading.Thread(target=self._run, args=(t, name), daemon=True).start()

    def _run(self, total, name):
        steps = {
            total:       f"MISSION: {name}",
            total - 2:   "SYSTEMS CHECK…",
            3:           "ARM SEQUENCE INITIATED",
            2:           "ARMING…",
            1:           "STAND CLEAR",
            0:           "LIFT-OFF!",
        }
        for t in range(total, -1, -1):
            if not self._running:
                return
            label = f"T-{t}" if t > 0 else "T-0"
            msg   = steps.get(t, "")
            self._win.after(0, self._cd_var.set, label)
            if msg:
                self._win.after(0, self._status_var.set, msg)
                self._log(f"[INAUGURATE] {label} — {msg}", GOLD)
            # Bell at each second
            self._win.after(0, lambda: self._win.bell())
            # Send ARM at T-2
            if t == 2:
                self._win.after(0, lambda: self._send({"cmd": "ARM"}))
            time.sleep(1)

        if self._running:
            # T-0: send HOVER to stabilize
            self._win.after(0, lambda: self._send({"cmd": "HOVER"}))
            self._win.after(0, self._status_var.set, "HOVER — drone is airborne!")
            self._log("[INAUGURATE] Sequence complete — HOVER sent", SUCCESS)
            self._win.after(3000, self._win.destroy)

    def _abort(self):
        self._running = False
        if hasattr(self, '_win') and self._win.winfo_exists():
            self._log("[INAUGURATE] ABORTED", DANGER)
            self._send({"cmd": "KILL"})
            self._win.destroy()


# ─────────────────────────────────────────────────────────────
#  PREFLIGHT RUNNER
# ─────────────────────────────────────────────────────────────
PREFLIGHT_TESTS = [
    ("connectivity", "1. Connectivity",  True),
    ("battery",      "2. Battery",       True),
    ("imu",          "3. IMU Level",     True),
    ("sonar",        "4. Sonar",         True),
    ("gps",          "5. GPS Fix",       False),
    ("motor_fl",     "6. Motor FL",      False),
    ("motor_fr",     "7. Motor FR",      False),
    ("motor_rl",     "8. Motor RL",      False),
    ("motor_rr",     "9. Motor RR",      False),
]


class PreflightRunner:
    """Runs automated hardware tests and reports results to UI callbacks."""

    STATUS_ICONS = {"idle": "○", "running": "◉", "pass": "✓", "fail": "✗", "skip": "—"}
    STATUS_COLORS = {"idle": SUBTEXT, "running": WARN,
                     "pass": SUCCESS, "fail": DANGER, "skip": SUBTEXT}

    def __init__(self, conn, get_latest_telem, get_gps, log, on_result, on_critical_pass):
        self._conn       = conn
        self._telem      = get_latest_telem   # () -> dict or None
        self._gps        = get_gps            # () -> dict
        self._log        = log
        self._on_result  = on_result          # (test_id, status) -> None
        self._on_crit    = on_critical_pass   # (bool) -> None
        self._stop_flag  = False

    def run_all(self):
        self._stop_flag = False
        threading.Thread(target=self._run_sequence,
                         args=(PREFLIGHT_TESTS,), daemon=True).start()

    def run_one(self, test_id):
        tests = [t for t in PREFLIGHT_TESTS if t[0] == test_id]
        if tests:
            threading.Thread(target=self._run_sequence,
                             args=(tests,), daemon=True).start()

    def stop(self):
        self._stop_flag = True

    def _run_sequence(self, tests):
        for tid, label, critical in tests:
            if self._stop_flag:
                break
            self._on_result(tid, "running")
            try:
                ok, msg = self._run_test(tid)
                status = "pass" if ok else "fail"
                self._log(f"[PREFLIGHT] {label}: {'PASS' if ok else 'FAIL'} — {msg}",
                          SUCCESS if ok else DANGER)
            except Exception as e:
                status = "fail"
                self._log(f"[PREFLIGHT] {label}: ERROR — {e}", DANGER)
            self._on_result(tid, status)

        # Check if all critical tests passed
        # (caller tracks results; we just signal completion)
        self._on_crit(None)   # trigger re-evaluation in the app

    def _run_test(self, tid):
        if not self._conn.connected:
            return False, "Not connected"

        # ── Connectivity ──────────────────────────────────────
        if tid == "connectivity":
            # Record timestamp BEFORE sending PING so we only accept
            # packets that arrive AFTER this point (prevents stale-cache
            # false positives when reconnecting to a silent FC).
            before_ts = self._telem_ts
            self._conn.send({"cmd": "PING"})
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if self._telem_ts > before_ts:
                    return True, "Fresh FC telemetry received"
                time.sleep(0.1)
            return False, "No FC telemetry in 5s — check ESP32↔Mega UART wiring"

        # ── Battery ───────────────────────────────────────────
        if tid == "battery":
            t = self._telem()
            if not t:
                return False, "No telemetry"
            mv = t.get("bat_mv", 0)
            if mv >= BAT_WARN_MV:
                return True, f"{mv} mV — OK"
            elif mv >= BAT_CRIT_MV:
                return False, f"{mv} mV — below warn threshold {BAT_WARN_MV} mV"
            else:
                return False, f"{mv} mV — CRITICAL (below {BAT_CRIT_MV} mV)"

        # ── IMU Level ─────────────────────────────────────────
        if tid == "imu":
            t = self._telem()
            if not t:
                return False, "No telemetry"
            roll  = abs(t.get("roll",  99))
            pitch = abs(t.get("pitch", 99))
            if roll < 5 and pitch < 5:
                return True, f"roll={roll:.1f}° pitch={pitch:.1f}°"
            return False, f"Drone not level: roll={roll:.1f}° pitch={pitch:.1f}°"

        # ── Sonar ─────────────────────────────────────────────
        if tid == "sonar":
            t = self._telem()
            if not t:
                return False, "No telemetry"
            alt = t.get("alt_cm", 0)
            if 0 < alt < 500:
                return True, f"{alt} cm"
            if alt == 0:
                return False, "Reading 0 — check D7/D8 wiring"
            return False, f"Unexpected value: {alt} cm"

        # ── GPS ───────────────────────────────────────────────
        if tid == "gps":
            g = self._gps()
            fix  = g.get("fix", 0)
            sats = g.get("sats", 0)
            if fix and sats >= 4:
                return True, f"fix={fix}  sats={sats}"
            if fix and sats == 0:
                return True, "fix=1  sats=N/A (browser GPS — no satellite count)"
            if not fix:
                return False, "No GPS fix — accuracy too low or no signal"
            return False, f"fix={fix}  sats={sats} — need ≥4 sats"

        # ── Motor tests ───────────────────────────────────────
        motor_map = {"motor_fl": "FL", "motor_fr": "FR",
                     "motor_rl": "RL", "motor_rr": "RR"}
        if tid in motor_map:
            motor = motor_map[tid]
            # Confirmation is shown by the UI — here we just send
            self._conn.send({"cmd":         "MOTOR_TEST",
                             "motor":       motor,
                             "throttle":    1100,
                             "duration_ms": 1500})
            # Wait up to 5s for ACK
            self._ack_event = threading.Event()
            self._ack_result = None
            deadline = time.time() + 5.0
            while time.time() < deadline and self._ack_result is None:
                time.sleep(0.1)
            if self._ack_result == "OK":
                return True, f"Motor {motor} spun OK"
            return False, f"No ACK for motor {motor} (props OFF?)"

        return False, f"Unknown test: {tid}"

    def notify_ack(self, pkt):
        """Called by RADHAApp._on_ack to feed ACKs into running motor tests."""
        if pkt.get("ack") == "MOTOR_TEST":
            self._ack_result = pkt.get("status", "ERR")


# ─────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────
class RADHAApp:

    def __init__(self, root):
        self.root = root
        self.root.title("RADHA GCS  ·  SUDARSHAN UAV")
        self.root.configure(bg=BG)
        self.root.geometry("1160x700")
        self.root.minsize(960, 580)

        self._armed              = False
        self._preset_segs        = []
        self._gps_vars           = {}
        self._fix_lbl            = None
        self._bat_lbl            = None
        self._last_seq           = -1
        self._latest_telem       = None
        self._telem_ts           = 0.0    # epoch of last REAL telemetry packet
        self._conn_time          = 0.0    # epoch when last connection was established
        self._no_telem_warned    = False  # one-shot "no FC data" warning fired
        self._latest_gps         = {}
        self._gps_fresh          = False  # True when a new GPS fix arrived from HTTPS server
        self._preflight_results  = {t[0]: "idle" for t in PREFLIGHT_TESTS}
        self._preflight_critical = False   # True when tests 1–4 all pass

        self._gps_https = GpsHttpsServer()

        self.flog   = FlightLog()
        crypto      = CryptoLayer(AES_KEY, ENCRYPT_ENABLED)

        self.conn   = ConnectionManager(
            on_telemetry = self._on_telem,
            on_ack       = self._on_ack,
            on_status    = self._on_conn_status,
            crypto       = crypto,
        )
        self.dms    = DeadManSwitch(DMS_TIMEOUT, self._dms_fired)
        self.pfrun  = PreflightRunner(
            conn             = self.conn,
            get_latest_telem = lambda: self._latest_telem,
            get_gps          = lambda: self._latest_gps,
            log              = self._log,
            on_result        = self._pf_result,
            on_critical_pass = self._pf_check_critical,
        )

        self._build_ui()
        self._switch_tab("FLIGHT")
        self._tick()
        self._gps_fwd_tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        enc_state = "AES-128-CBC" if ENCRYPT_ENABLED else "plaintext"
        self._log(f"GCS v1.2 — encryption: {enc_state}", SUBTEXT)

        # Start HTTPS GPS server (serves GPS page so any browser can stream GPS)
        self._gps_https.set_gps_callback(self._on_phone_gps_https)
        https_url = self._gps_https.start(log_fn=self._log)
        if https_url:
            self._log(f"GPS page (HTTPS, works on all browsers): {https_url}", SUCCESS)
            self._log("  → Phone: connect to SUDARSHAN_AP → open that URL → tap START GPS", SUBTEXT)
            self._log("  → First time: tap 'Advanced → Proceed' past the cert warning", SUBTEXT)

    def _on_close(self):
        self._gps_https.stop()
        self.flog.close()
        self.root.destroy()

    def _on_phone_gps_https(self, data: dict):
        """GPS data arrived from phone via the GCS HTTPS endpoint."""
        acc = float(data.get("acc", 999.0))
        self._latest_gps = {
            "lat":     float(data.get("lat", 0.0)),
            "lon":     float(data.get("lon", 0.0)),
            "alt":     float(data.get("alt", 0.0)),
            "heading": float(data.get("heading", 0.0)),
            "baro_cm": 0,
            "fix":     1 if acc < 100.0 else 0,
            "sats":    0,
        }
        self._gps_fresh = True
        self.root.after(0, self._apply_gps, self._latest_gps)

    def _gps_fwd_tick(self):
        """Forward fresh GPS from HTTPS server to ESP32 at 5 Hz."""
        if self._gps_fresh and self.conn.connected:
            self._gps_fresh = False
            g = self._latest_gps
            self.conn.send({
                "cmd":     "GPS",
                "lat":     g.get("lat", 0.0),
                "lon":     g.get("lon", 0.0),
                "alt":     g.get("alt", 0.0),
                "heading": g.get("heading", 0.0),
                "baro_cm": 0,
                "fix":     g.get("fix", 0),
                "sats":    0,
            })
        self.root.after(200, self._gps_fwd_tick)

    # ── UI BUILD ─────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self.root, bg=SIDEBAR, height=46)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="RADHA GCS", bg=SIDEBAR, fg=ACCENT,
                 font=("Consolas", 13, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(top, text="SUDARSHAN UAV", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(side="left", pady=10)

        self._dms_lbl  = tk.Label(top, text="DMS: --s",
                                   bg=SIDEBAR, fg=SUBTEXT, font=F_SMALL)
        self._dms_lbl.pack(side="right", padx=10)
        self._conn_lbl = tk.Label(top, text="● DISCONNECTED",
                                   bg=SIDEBAR, fg=SUBTEXT, font=F_BODY)
        self._conn_lbl.pack(side="right", padx=10)
        self._mode_lbl = tk.Label(top, text="MODE: ---",
                                   bg=SIDEBAR, fg=WARN, font=F_HEAD)
        self._mode_lbl.pack(side="right", padx=14)
        self._arm_lbl  = tk.Label(top, text="DISARMED",
                                   bg=SIDEBAR, fg=DANGER, font=F_HEAD)
        self._arm_lbl.pack(side="right", padx=14)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        sb = tk.Frame(body, bg=SIDEBAR, width=120)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        self._tab_btns = {}
        for name in ("FLIGHT", "PRESET", "PREFLIGHT"):
            b = tk.Button(sb, text=name, bg=SIDEBAR, fg=SUBTEXT,
                          font=F_BODY, relief="flat", cursor="hand2",
                          activebackground=PANEL, activeforeground=ACCENT,
                          command=lambda n=name: self._switch_tab(n))
            b.pack(fill="x", padx=4, pady=2, ipady=10)
            self._tab_btns[name] = b

        cf = tk.Frame(sb, bg=SIDEBAR)
        cf.pack(side="bottom", fill="x", padx=6, pady=8)
        tk.Label(cf, text="ESP32 IP", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w")
        self._ip_var   = tk.StringVar(value=ESP32_IP)
        tk.Entry(cf, textvariable=self._ip_var, bg=PANEL, fg=TEXT,
                 font=F_SMALL, insertbackground=TEXT, relief="flat").pack(fill="x", pady=2)
        tk.Label(cf, text="Port", bg=SIDEBAR, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w")
        self._port_var = tk.StringVar(value=str(ESP32_PORT))
        tk.Entry(cf, textvariable=self._port_var, bg=PANEL, fg=TEXT,
                 font=F_SMALL, insertbackground=TEXT, relief="flat").pack(fill="x", pady=2)
        self._conn_btn = tk.Button(cf, text="CONNECT", bg=ACCENT, fg=BG,
                                    font=F_BODY, relief="flat", cursor="hand2",
                                    command=self._toggle_connect)
        self._conn_btn.pack(fill="x", pady=6, ipady=4)

        self._content = tk.Frame(body, bg=BG)
        self._content.pack(fill="both", expand=True, padx=8, pady=8)

        self._panels = {
            "FLIGHT":    self._build_flight_panel(self._content),
            "PRESET":    self._build_preset_panel(self._content),
            "PREFLIGHT": self._build_preflight_panel(self._content),
        }

    def _switch_tab(self, name):
        for t, btn in self._tab_btns.items():
            btn.config(fg=ACCENT if t == name else SUBTEXT,
                       bg=PANEL  if t == name else SIDEBAR)
        for t, panel in self._panels.items():
            (panel.pack(fill="both", expand=True)
             if t == name else panel.pack_forget())

    # ── FLIGHT PANEL ─────────────────────────────────────────

    def _build_flight_panel(self, parent):
        f  = tk.Frame(parent, bg=BG)
        tl = tk.Frame(f, bg=PANEL)
        tl.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(tl, text="TELEMETRY", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 6))

        self._tv = {}
        rows = [("ROLL","roll","°"), ("PITCH","pitch","°"), ("YAW","yaw","°"),
                ("ALT","alt_cm","cm"), ("BATTERY","bat_mv","mV"), ("MODE","mode","")]
        g = tk.Frame(tl, bg=PANEL)
        g.pack(fill="x", padx=12)
        for i, (lbl, key, unit) in enumerate(rows):
            tk.Label(g, text=lbl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL, width=8, anchor="w").grid(row=i, column=0, pady=4)
            v = tk.StringVar(value="---")
            self._tv[key] = v
            w = tk.Label(g, textvariable=v, bg=PANEL, fg=TEXT, font=F_BIG, anchor="w")
            w.grid(row=i, column=1, sticky="w", padx=8)
            tk.Label(g, text=unit, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL).grid(row=i, column=2, sticky="w")
            if key == "bat_mv":
                self._bat_lbl = w

        tk.Label(tl, text="ATTITUDE", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(14, 0))
        self._att = tk.Canvas(tl, bg="#111", width=190, height=190, highlightthickness=0)
        self._att.pack(padx=12, pady=6)
        self._draw_ati(0, 0)

        tk.Label(tl, text="GPS / PHONE", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 4))
        gg = tk.Frame(tl, bg=PANEL)
        gg.pack(fill="x", padx=12, pady=(0, 10))
        for i, (ttl, key) in enumerate([("FIX","fix"), ("SATS","sats"), ("LAT","lat"),
                                         ("LON","lon"), ("HEADING","heading"), ("BARO","baro_cm")]):
            tk.Label(gg, text=ttl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL, width=8, anchor="w").grid(row=i, column=0, pady=3)
            v = tk.StringVar(value="---")
            self._gps_vars[key] = v
            w = tk.Label(gg, textvariable=v, bg=PANEL, fg=TEXT, font=F_BODY, anchor="w")
            w.grid(row=i, column=1, sticky="w", padx=8)
            if key == "fix":
                self._fix_lbl = w

        rc = tk.Frame(f, bg=PANEL, width=260)
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

        tk.Frame(rc, bg=PANEL, height=4).pack()
        tk.Button(rc, text="⚠  KILL", bg=DANGER, fg="white",
                  font=("Consolas", 12, "bold"), relief="flat", cursor="hand2",
                  command=self._kill_confirm).pack(fill="x", padx=12, pady=3, ipady=12)

        tk.Frame(rc, bg=PANEL, height=4).pack()
        tk.Button(rc, text="★  INAUGURATE", bg=GOLD, fg="#000",
                  font=F_HEAD, relief="flat", cursor="hand2",
                  command=self._inauguration).pack(fill="x", padx=12, pady=3, ipady=10)

        # Preflight interlock notice
        self._pf_notice = tk.Label(rc, text="⚠ Run PREFLIGHT before ARM",
                                    bg=PANEL, fg=WARN, font=F_SMALL, wraplength=220)
        self._pf_notice.pack(padx=12, pady=(4, 0))

        tk.Label(rc, text="LOG", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(10, 2))
        self._log_box = tk.Text(rc, bg="#080808", fg=TEXT, font=("Consolas", 8),
                                 relief="flat", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        return f

    def _draw_ati(self, roll_deg, pitch_deg):
        c = self._att
        c.delete("all")
        cx, cy, r = 95, 95, 82
        ang    = math.radians(-roll_deg)
        pp     = pitch_deg * 1.8
        dx, dy = r * math.sin(ang), r * math.cos(ang)
        sky_pts = [cx-dx, cy-dy+pp, cx+dx, cy+dy+pp,
                   cx+dx+250, cy+dy+pp-250, cx-dx-250, cy-dy+pp-250]
        c.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#162030", outline="")
        c.create_polygon(sky_pts, fill="#1a1a00")
        c.create_line(cx-dx, cy-dy+pp, cx+dx, cy+dy+pp, fill="white", width=2)
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=PANEL, width=14)
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=SUBTEXT, width=1)
        c.create_line(cx-22, cy, cx-7,  cy, fill=ACCENT, width=2)
        c.create_line(cx+7,  cy, cx+22, cy, fill=ACCENT, width=2)
        c.create_rectangle(cx-3, cy-3, cx+3, cy+3, fill=ACCENT, outline="")

    # ── PRESET PANEL ─────────────────────────────────────────

    def _build_preset_panel(self, parent):
        f  = tk.Frame(parent, bg=BG)
        lf = tk.Frame(f, bg=PANEL)
        lf.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(lf, text="PRESET FLIGHT PATH", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(lf, text="IMU dead-reckoning  ·  relative metre waypoints",
                 bg=PANEL, fg=SUBTEXT, font=F_SMALL).pack(anchor="w", padx=12)

        ir = tk.Frame(lf, bg=PANEL)
        ir.pack(fill="x", padx=12, pady=10)
        self._e = {}
        for lbl, key, w in (("Bearing °","bearing",6), ("Dist m","dist",6), ("Speed","speed",5)):
            tk.Label(ir, text=lbl, bg=PANEL, fg=SUBTEXT,
                     font=F_SMALL).pack(side="left", padx=(0, 2))
            e = tk.Entry(ir, bg="#1a1a1a", fg=TEXT, font=F_BODY,
                         width=w, insertbackground=TEXT, relief="flat")
            e.pack(side="left", padx=(0, 10))
            self._e[key] = e
        tk.Button(ir, text="ADD", bg=ACCENT, fg=BG, font=F_BODY,
                  relief="flat", cursor="hand2",
                  command=self._add_seg).pack(side="left", ipady=4, ipadx=10)

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

        br = tk.Frame(lf, bg=PANEL)
        br.pack(fill="x", padx=12, pady=8)
        tk.Button(br, text="REMOVE SEL", bg=WARN, fg=BG, font=F_SMALL,
                  relief="flat", cursor="hand2",
                  command=self._remove_seg).pack(side="left", ipady=4, ipadx=8)
        tk.Button(br, text="CLEAR ALL", bg=DANGER, fg="white", font=F_SMALL,
                  relief="flat", cursor="hand2",
                  command=self._clear_segs).pack(side="left", padx=8, ipady=4, ipadx=8)
        tk.Button(br, text="▶  EXECUTE PRESET", bg=SUCCESS, fg=BG, font=F_HEAD,
                  relief="flat", cursor="hand2",
                  command=self._exec_preset).pack(side="right", ipady=6, ipadx=14)

        rf = tk.Frame(f, bg=PANEL, width=290)
        rf.pack(side="right", fill="both")
        rf.pack_propagate(False)
        tk.Label(rf, text="PATH PREVIEW", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(10, 4))
        self._pcanvas = tk.Canvas(rf, bg="#080808", highlightthickness=0)
        self._pcanvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._pcanvas.bind("<Configure>", lambda e: self._draw_preview())
        return f

    # ── PREFLIGHT PANEL ──────────────────────────────────────

    def _build_preflight_panel(self, parent):
        f = tk.Frame(parent, bg=BG)

        lf = tk.Frame(f, bg=PANEL)
        lf.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(lf, text="HARDWARE PREFLIGHT TESTS", bg=PANEL, fg=ACCENT,
                 font=F_HEAD).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(lf, text="PROPS OFF during motor tests  ·  Critical tests unlock ARM",
                 bg=PANEL, fg=SUBTEXT, font=F_SMALL).pack(anchor="w", padx=12)

        # Test rows
        self._pf_icon  = {}
        self._pf_label = {}
        tbl = tk.Frame(lf, bg=PANEL)
        tbl.pack(fill="x", padx=12, pady=10)

        for row, (tid, label, critical) in enumerate(PREFLIGHT_TESTS):
            crit_tag = " ★" if critical else ""
            icon_var = tk.StringVar(value="○")
            col_var  = SUBTEXT
            icon_lbl = tk.Label(tbl, textvariable=icon_var, bg=PANEL,
                                 fg=col_var, font=("Consolas", 14, "bold"), width=3)
            icon_lbl.grid(row=row, column=0, padx=(0, 6), pady=3)
            tk.Label(tbl, text=label + crit_tag, bg=PANEL, fg=TEXT,
                     font=F_BODY, width=22, anchor="w").grid(row=row, column=1, pady=3)
            tk.Button(tbl, text="RUN", bg=PANEL, fg=ACCENT, font=F_SMALL,
                      relief="flat", cursor="hand2",
                      command=lambda t=tid: self._pf_run_one(t)).grid(
                row=row, column=2, padx=8, pady=3, ipadx=6)
            self._pf_icon[tid]  = (icon_lbl, icon_var)

        # Buttons
        br = tk.Frame(lf, bg=PANEL)
        br.pack(fill="x", padx=12, pady=10)
        tk.Button(br, text="▶  RUN ALL TESTS", bg=SUCCESS, fg=BG, font=F_HEAD,
                  relief="flat", cursor="hand2",
                  command=self._pf_run_all).pack(side="left", ipady=6, ipadx=14)
        tk.Button(br, text="RESET", bg=SUBTEXT, fg=BG, font=F_SMALL,
                  relief="flat", cursor="hand2",
                  command=self._pf_reset).pack(side="left", padx=8, ipady=6, ipadx=10)

        self._pf_status_lbl = tk.Label(lf, text="", bg=PANEL, fg=SUBTEXT, font=F_SMALL)
        self._pf_status_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        # Right: test log
        rf = tk.Frame(f, bg=PANEL, width=300)
        rf.pack(side="right", fill="both")
        rf.pack_propagate(False)
        tk.Label(rf, text="TEST LOG", bg=PANEL, fg=SUBTEXT,
                 font=F_SMALL).pack(anchor="w", padx=12, pady=(10, 4))
        self._pf_log = tk.Text(rf, bg="#080808", fg=TEXT, font=("Consolas", 8),
                                relief="flat", state="disabled")
        self._pf_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        return f

    def _pf_run_all(self):
        if not self.conn.connected:
            self._pf_log_add("Not connected to ESP32.", DANGER)
            return
        self._pf_log_add("── Running all preflight tests ──", ACCENT)
        # Motor tests need confirmation
        if not messagebox.askyesno("Motor Test Safety",
                                   "Motor tests will spin each motor briefly.\n"
                                   "CONFIRM: propellers are REMOVED?",
                                   icon="warning"):
            self._pf_log_add("Motor tests skipped (props safety).", WARN)
            # Run non-motor tests only
            tests = [t for t in PREFLIGHT_TESTS if not t[0].startswith("motor")]
            self.pfrun._stop_flag = False
            threading.Thread(target=self.pfrun._run_sequence,
                             args=(tests,), daemon=True).start()
            return
        self.pfrun.run_all()

    def _pf_run_one(self, tid):
        if not self.conn.connected:
            self._pf_log_add("Not connected.", DANGER)
            return
        if tid.startswith("motor"):
            if not messagebox.askyesno("Motor Test Safety",
                                       "This will spin one motor briefly.\n"
                                       "CONFIRM: propellers are REMOVED?",
                                       icon="warning"):
                return
        self._pf_log_add(f"Running: {tid}…", ACCENT)
        self.pfrun.run_one(tid)

    def _pf_reset(self):
        for tid in self._preflight_results:
            self._preflight_results[tid] = "idle"
            self._pf_update_icon(tid, "idle")
        self._preflight_critical = False
        self._pf_status_lbl.config(text="", fg=SUBTEXT)
        self._pf_notice.config(text="⚠ Run PREFLIGHT before ARM", fg=WARN)

    def _pf_result(self, tid, status):
        self._preflight_results[tid] = status
        self.root.after(0, self._pf_update_icon, tid, status)

    def _pf_update_icon(self, tid, status):
        if tid not in self._pf_icon:
            return
        lbl, var = self._pf_icon[tid]
        var.set(PreflightRunner.STATUS_ICONS.get(status, "?"))
        lbl.config(fg=PreflightRunner.STATUS_COLORS.get(status, SUBTEXT))

    def _pf_check_critical(self, _):
        critical_ids = [t[0] for t in PREFLIGHT_TESTS if t[2]]
        all_pass = all(self._preflight_results.get(tid) == "pass"
                       for tid in critical_ids)
        self._preflight_critical = all_pass
        def _update():
            if all_pass:
                self._pf_status_lbl.config(
                    text="✓ Critical tests passed — ARM unlocked", fg=SUCCESS)
                self._pf_notice.config(text="✓ Preflight passed", fg=SUCCESS)
            else:
                failed = [tid for tid in critical_ids
                          if self._preflight_results.get(tid) == "fail"]
                self._pf_status_lbl.config(
                    text=f"✗ Failing: {', '.join(failed)}", fg=DANGER)
        self.root.after(0, _update)

    def _pf_log_add(self, msg, color=TEXT):
        def _do():
            self._pf_log.config(state="normal")
            ts  = time.strftime("%H:%M:%S")
            tag = f"c_{color.replace('#','')}"
            self._pf_log.tag_config(tag, foreground=color)
            self._pf_log.insert("end", f"[{ts}] {msg}\n", tag)
            self._pf_log.see("end")
            self._pf_log.config(state="disabled")
        self.root.after(0, _do)

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
        self._tree.insert("", "end", values=(n, f"{bearing:.1f}°", f"{dist:.1f}", f"{speed:.2f}"))
        for k in ("bearing", "dist", "speed"):
            self._e[k].delete(0, "end")
        self._draw_preview()

    def _remove_seg(self):
        sel = self._tree.selection()
        if not sel:
            return
        self._tree.delete(sel[0])
        self._preset_segs.pop(self._tree.index(sel[0]) if sel[0] in self._tree.get_children() else 0)
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
            self._log("No segments defined", WARN); return
        if not self.conn.connected:
            self._log("Not connected", DANGER); return
        if not self._armed:
            self._log("Arm the drone first", WARN); return
        if self.conn.send({"cmd": "PRESET", "segments": self._preset_segs}):
            self._log(f"PRESET → {len(self._preset_segs)} segments sent", SUCCESS)

    def _draw_preview(self):
        c = self._pcanvas
        c.update_idletasks()
        W = c.winfo_width()  or 270
        H = c.winfo_height() or 420
        c.delete("all")
        for x in range(0, W, 30): c.create_line(x, 0, x, H, fill="#151515")
        for y in range(0, H, 30): c.create_line(0, y, W, y, fill="#151515")
        if not self._preset_segs:
            c.create_text(W//2, H//2, text="No path defined", fill=SUBTEXT, font=F_SMALL)
            return
        px, py = 0.0, 0.0
        pts = [(px, py)]
        for seg in self._preset_segs:
            r = math.radians(seg["bearing"])
            px += seg["dist_m"] * math.sin(r)
            py -= seg["dist_m"] * math.cos(r)
            pts.append((px, py))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        span = max(max(xs)-min(xs), max(ys)-min(ys), 1)
        sc   = min(W, H) * 0.72 / span
        ox   = W/2 - (sum(xs)/len(xs))*sc
        oy   = H/2 - (sum(ys)/len(ys))*sc
        for i in range(1, len(pts)):
            x1,y1 = pts[i-1][0]*sc+ox, pts[i-1][1]*sc+oy
            x2,y2 = pts[i  ][0]*sc+ox, pts[i  ][1]*sc+oy
            c.create_line(x1,y1,x2,y2, fill=ACCENT, width=2,
                          arrow="last", arrowshape=(8,10,3))
            c.create_text((x1+x2)/2+6,(y1+y2)/2, anchor="w",
                          text=f"{self._preset_segs[i-1]['dist_m']:.1f}m",
                          fill=SUBTEXT, font=("Consolas",7))
        for i,(wpx,wpy) in enumerate(pts):
            x,y = wpx*sc+ox, wpy*sc+oy
            col = SUCCESS if i==0 else (DANGER if i==len(pts)-1 else WARN)
            c.create_oval(x-5,y-5,x+5,y+5, fill=col, outline="")
            c.create_text(x+8,y, anchor="w", text=str(i), fill=col, font=("Consolas",7))

    # ── Commands ─────────────────────────────────────────────

    def _send_cmd(self, cmd: str):
        if not self.conn.connected:
            self._log("Not connected to ESP32", DANGER); return
        # ARM interlock: warn if preflight not passed
        if cmd == "ARM" and not self._preflight_critical:
            if not messagebox.askyesno(
                    "Preflight Not Complete",
                    "Critical preflight tests have not all passed.\n"
                    "ARM anyway?", icon="warning"):
                return
        if self.conn.send({"cmd": cmd}):
            self._log(f"→ {cmd}", ACCENT)
            self.dms.reset()

    def _kill_confirm(self):
        if messagebox.askyesno("KILL MOTORS",
                               "Send KILL?\nThis cuts all motors immediately!",
                               icon="warning"):
            self._send_cmd("KILL")

    def _inauguration(self):
        if not self.conn.connected:
            self._log("Connect to ESP32 first", DANGER); return
        InaugurationDialog(self.root,
                           send_cmd=lambda p: self.conn.send(p),
                           log=self._log)

    # ── Callbacks ────────────────────────────────────────────

    def _on_telem(self, pkt):
        if "info" in pkt:
            info = pkt["info"]
            colors = {"GCS_CONNECTED": SUCCESS,
                      "PHONE_CONNECTED": SUCCESS,
                      "PHONE_DISCONNECTED": WARN}
            col = colors.get(info, SUBTEXT)
            self.root.after(0, self._log, f"ESP32: {info}", col)
            self.flog.write(f"INFO {info}")
            return
        if "dms" in pkt:
            action = pkt.get("action", "?")
            self.root.after(0, self._log, f"⚠ ESP32 DMS FIRED — {action}", DANGER)
            self.flog.write(f"DMS FIRED action={action}")
            return
        if pkt.get("type") == "phone":
            self._latest_gps = pkt
            self.root.after(0, self._apply_gps, pkt)
        else:
            # Sequence gap detection
            seq = pkt.get("seq", -1)
            if seq >= 0 and self._last_seq >= 0:
                gap = (seq - self._last_seq) & 0xFFFF
                if gap > 1:
                    self.root.after(0, self._log,
                                    f"⚠ TELEM GAP: missed {gap-1} packet(s)", WARN)
            if seq >= 0:
                self._last_seq = seq
            self._latest_telem    = pkt
            self._telem_ts        = time.time()
            self._no_telem_warned = True   # suppress the "no FC data" warning
            self.flog.write_telem(pkt)
            self.root.after(0, self._apply_telem, pkt)

    def _apply_telem(self, pkt):
        for key, var in self._tv.items():
            val = pkt.get(key, "---")
            var.set(f"{val:.1f}" if isinstance(val, float) else str(val))
        bat_mv = pkt.get("bat_mv", 0)
        if self._bat_lbl:
            if bat_mv > 0 and bat_mv < BAT_CRIT_MV:
                self._bat_lbl.config(fg=DANGER)
            elif bat_mv > 0 and bat_mv < BAT_WARN_MV:
                self._bat_lbl.config(fg=WARN)
            else:
                self._bat_lbl.config(fg=TEXT)
        if pkt.get("warn") == "SONAR_STALE":
            self._log("⚠ SONAR STALE — altitude hold unreliable", WARN)
        armed = pkt.get("armed", False)
        self._armed = armed
        self._arm_lbl.config(text="ARMED" if armed else "DISARMED",
                              fg=SUCCESS if armed else DANGER)
        self._mode_lbl.config(text=f"MODE: {pkt.get('mode','---')}")
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
        self.pfrun.notify_ack(pkt)   # feed into any running preflight motor test
        cmd, st = pkt.get("ack","?"), pkt.get("status","?")
        msg  = pkt.get("msg","")
        col  = SUCCESS if st == "OK" else DANGER
        full = f"ACK {cmd}: {st} {msg}".strip()
        self.flog.write(full)
        self.root.after(0, self._log, full, col)
        # Mirror motor test results to preflight log
        if cmd == "MOTOR_TEST":
            self.root.after(0, self._pf_log_add, full,
                            SUCCESS if st == "OK" else DANGER)

    def _on_conn_status(self, msg, col):
        self.flog.write(f"CONN {msg}")
        def _do():
            self._conn_lbl.config(text=f"● {msg}", fg=col)
            connected = ("CONNECTED" in msg
                         and "DIS" not in msg
                         and "RECONNECT" not in msg)
            self._conn_btn.config(
                text="DISCONNECT" if connected else "CONNECT")
            if connected:
                self.dms.start()
                self._conn_time       = time.time()
                self._no_telem_warned = False
                # Clear stale telemetry from a previous session so preflight
                # tests don't read old cached data and false-positive.
                self._latest_telem    = None
                self._telem_ts        = 0.0
            elif "DISCONNECTED" in msg and "RECONNECT" not in msg:
                self.dms.stop()
                self._latest_telem    = None
                self._telem_ts        = 0.0
                self._no_telem_warned = False
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

    def _tick(self):
        if self.conn.connected:
            self.conn.send({"cmd": "PING"})
            rem = self.dms.remaining()
            self._dms_lbl.config(
                text=f"DMS: {rem:.0f}s",
                fg=DANGER if rem < 8 else (WARN if rem < 15 else SUBTEXT))
            # Warn once if connected but no FC telemetry after 5 s
            if (not self._no_telem_warned
                    and self._conn_time > 0
                    and self._telem_ts == 0.0
                    and time.time() - self._conn_time > 5.0):
                self._no_telem_warned = True
                self._log("⚠ Connected to ESP32 but no FC telemetry received — "
                          "check ESP32↔Mega UART wiring (TX/RX, common GND, "
                          "voltage divider on Mega→ESP32 line)", WARN)
        else:
            self._dms_lbl.config(text="DMS: --s", fg=SUBTEXT)
        self.root.after(1000, self._tick)

    def _log(self, msg, color=TEXT):
        def _do():
            self._log_box.config(state="normal")
            ts  = time.strftime("%H:%M:%S")
            tag = f"c_{color.replace('#','')}"
            self._log_box.tag_config(tag, foreground=color)
            self._log_box.insert("end", f"[{ts}] {msg}\n", tag)
            self._log_box.see("end")
            lines = int(self._log_box.index("end-1c").split(".")[0])
            if lines > LOG_MAX_LINES:
                self._log_box.delete("1.0", f"{lines - LOG_MAX_LINES + 200}.0")
            self._log_box.config(state="disabled")
        self.root.after(0, _do)


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()   # hide main window until login succeeds

    login = LoginDialog(root)
    if not login.result:
        sys.exit(0)

    root.deiconify()
    app = RADHAApp(root)
    root.mainloop()
