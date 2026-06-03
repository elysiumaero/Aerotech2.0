/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║       SUDARSHAN ESP32 BRIDGE FIRMWARE v2.0                  ║
 * ║       Project : RADHA / SUDARSHAN UAV                       ║
 * ║       Role    : WiFi AP ↔ UART bridge                       ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║                                                              ║
 * ║   ✦  With love and gratitude to Neelrisham Singh  ✦        ║
 * ║      For your endless support, belief, and love.            ║
 * ║      Every flight carries a piece of you.   — Sudarshan    ║
 * ║                                                              ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  WIRING                                                      ║
 * ║    ESP32 GPIO17 (TX2) ──────────────► Mega2560 RX0 (Pin 0)  ║
 * ║    ESP32 GPIO16 (RX2) ◄──[DIVIDER]── Mega2560 TX0 (Pin 1)   ║
 * ║    Voltage divider on Mega TX:                               ║
 * ║      Mega TX ──[10kΩ]──┬──[20kΩ]── GND                     ║
 * ║                        └──► ESP32 GPIO16                    ║
 * ║    GND ────────────────────────────── GND (common)          ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  NETWORK (credentials in credentials.h)                     ║
 * ║    AP IP    : 192.168.4.1                                    ║
 * ║    GCS      → 192.168.4.1 : 5760  (TCP)                     ║
 * ║    Phone    → 192.168.4.1 : 5762  (TCP, NMEA from GPS Svr)  ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  DEPENDENCIES                                                ║
 * ║    ArduinoJson v6  (Library Manager → search ArduinoJson)   ║
 * ║    mbedTLS — built into ESP32 Arduino SDK (no install)       ║
 * ╚══════════════════════════════════════════════════════════════╝
 *
 * ── Phone GPS: GPS Server by Metrologic (NMEA client mode) ────
 *  Configure GPS Server app: TCP client → 192.168.4.1:5762
 *  ESP32 receives NMEA sentences ($GPGGA, $GPRMC, $GNGGA, $GNRMC)
 *  and converts to internal GPS struct forwarded to FC at 5 Hz.
 *
 * ── Encryption (set ENCRYPT_ENABLED in credentials.h) ─────────
 *  AES-128-CBC, PSK from credentials.h AES_KEY_HEX.
 *  Wire format: base64(16-byte-IV + AES_CBC(PKCS7-padded-JSON)) + "\n"
 *  Set ENCRYPT_ENABLED 0 to use plaintext (default — for bench test).
 */

#include <WiFi.h>
#include <WebSocketsServer.h>   // arduinoWebSockets by Markus Sattler — install via Library Manager
#include <WebServer.h>
#include <ArduinoJson.h>
#include "mbedtls/aes.h"
#include "mbedtls/base64.h"
#include "credentials.h"   // WIFI_SSID, WIFI_PASS, AES_KEY_HEX, ENCRYPT_ENABLED

// ─────────────────────────────────────────────────────────────
//  CONFIG
// ─────────────────────────────────────────────────────────────
#define PORT_GCS       5760
#define PORT_PHONE     5762

#define FC_RX_PIN      16
#define FC_TX_PIN      17
#define FC_BAUD        115200

#define DMS_TIMEOUT_MS 30000UL
#define GPS_FWD_MS     200UL
#define LED_PIN        2
#define ADMIN_PASS     "SUDARSHAN2025"   // change to your preferred password
#define PRIORITY_PASS  "1410"            // unlocks web GCS while Python GCS is on TCP
#define MASTER_PASS    "980752"          // accepted for ALL auth checks (super-admin)

static const IPAddress AP_IP (192, 168, 4, 1);
static const IPAddress AP_GW (192, 168, 4, 1);
static const IPAddress AP_SN (255, 255, 255, 0);

// ─────────────────────────────────────────────────────────────
//  CRYPTO
// ─────────────────────────────────────────────────────────────
static uint8_t aesKey[16];   // decoded from AES_KEY_HEX at setup

void initCrypto() {
  const char* h = AES_KEY_HEX;
  for (int i = 0; i < 16; i++) {
    char buf[3] = {h[i*2], h[i*2+1], 0};
    aesKey[i] = (uint8_t)strtol(buf, nullptr, 16);
  }
}

// Returns base64(IV + AES_CBC(PKCS7(plain))) or plain if encryption off
String encryptLine(const String& plain) {
#if !ENCRYPT_ENABLED
  return plain;
#endif
  // PKCS7 padding
  int plen   = plain.length();
  int pad    = 16 - (plen % 16);
  int padded = plen + pad;
  uint8_t* buf = (uint8_t*)malloc(padded);
  if (!buf) return plain;
  memcpy(buf, plain.c_str(), plen);
  memset(buf + plen, pad, pad);

  // Random IV
  uint8_t iv[16], iv_copy[16];
  esp_fill_random(iv, 16);
  memcpy(iv_copy, iv, 16);

  // AES-CBC encrypt in-place
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  mbedtls_aes_setkey_enc(&ctx, aesKey, 128);
  mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_ENCRYPT, padded, iv_copy, buf, buf);
  mbedtls_aes_free(&ctx);

  // Prepend IV
  int total = 16 + padded;
  uint8_t* combined = (uint8_t*)malloc(total);
  if (!combined) { free(buf); return plain; }
  memcpy(combined, iv, 16);
  memcpy(combined + 16, buf, padded);
  free(buf);

  // Base64 encode
  size_t b64len = 0;
  mbedtls_base64_encode(nullptr, 0, &b64len, combined, total);
  uint8_t* b64 = (uint8_t*)malloc(b64len + 1);
  if (!b64) { free(combined); return plain; }
  mbedtls_base64_encode(b64, b64len, &b64len, combined, total);
  b64[b64len] = 0;
  free(combined);

  String result = String((char*)b64);
  free(b64);
  return result;
}

// Decrypts a base64(IV+cipher) string back to plaintext JSON
String decryptLine(const String& b64str) {
#if !ENCRYPT_ENABLED
  return b64str;
#endif
  // Base64 decode
  size_t decLen = 0;
  mbedtls_base64_decode(nullptr, 0, &decLen,
                        (const uint8_t*)b64str.c_str(), b64str.length());
  if (decLen < 17) return "";
  uint8_t* decoded = (uint8_t*)malloc(decLen);
  if (!decoded) return "";
  mbedtls_base64_decode(decoded, decLen, &decLen,
                        (const uint8_t*)b64str.c_str(), b64str.length());

  uint8_t iv[16];
  memcpy(iv, decoded, 16);
  int cipherLen = decLen - 16;

  // AES-CBC decrypt
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  mbedtls_aes_setkey_dec(&ctx, aesKey, 128);
  mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_DECRYPT, cipherLen, iv, decoded + 16, decoded + 16);
  mbedtls_aes_free(&ctx);

  // Strip PKCS7 padding
  int padVal  = decoded[decLen - 1];
  int plainLen = cipherLen - padVal;
  if (plainLen <= 0 || plainLen >= (int)decLen) { free(decoded); return ""; }
  decoded[16 + plainLen] = 0;

  String result = String((char*)(decoded + 16));
  free(decoded);
  return result;
}

// ─────────────────────────────────────────────────────────────
//  GPS STATE  (must be before NMEA parsing and HTTP handlers)
// ─────────────────────────────────────────────────────────────
struct {
  double lat     = 0.0;
  double lon     = 0.0;
  float  alt     = 0.0;
  float  heading = 0.0;
  int    baro_cm = 0;
  int    fix     = 0;
  int    sats    = 0;
  bool   fresh   = false;
} gps;

// ─────────────────────────────────────────────────────────────
//  NMEA PARSING  (GPS Server by Metrologic, client mode)
// ─────────────────────────────────────────────────────────────

// Validate NMEA checksum — XOR of chars between '$' and '*'.
// Returns true if checksum matches OR if no '*' is present (some apps omit it).
bool nmeaChecksum(const String& s) {
  int star = s.indexOf('*');
  if (star < 2) return true;                       // no checksum — accept
  if (star + 2 > (int)s.length()) return true;    // truncated — accept
  uint8_t calc = 0;
  for (int i = 1; i < star; i++) calc ^= (uint8_t)s[i];
  char hex[3] = {s[star+1], s[star+2], 0};
  bool ok = (calc == (uint8_t)strtol(hex, nullptr, 16));
  if (!ok) Serial.printf("[NMEA ] Checksum FAIL: calc=%02X sent=%s  %.40s\n",
                          calc, hex, s.c_str());
  return ok;
}

// Return Nth comma-delimited field (0-indexed)
String nmeaField(const String& s, int n) {
  int start = 0, count = 0;
  for (int i = 0; i <= (int)s.length(); i++) {
    if (i == (int)s.length() || s[i] == ',') {
      if (count++ == n) return s.substring(start, i);
      start = i + 1;
    }
  }
  return "";
}

// Convert NMEA DDMM.MMMM + hemisphere to decimal degrees
double nmeaToDecimal(const String& field, char hemi) {
  if (field.length() < 3) return 0.0;
  double raw  = field.toDouble();
  int    deg  = (int)(raw / 100);
  double mins = raw - deg * 100.0;
  double dec  = deg + mins / 60.0;
  if (hemi == 'S' || hemi == 'W') dec = -dec;
  return dec;
}

// Parse $GPGGA / $GNGGA → fix, sats, lat, lon, alt
void parseGGA(const String& s) {
  if (!nmeaChecksum(s)) return;
  String latF  = nmeaField(s, 2);
  char   latH  = nmeaField(s, 3)[0];
  String lonF  = nmeaField(s, 4);
  char   lonH  = nmeaField(s, 5)[0];
  int    fix   = nmeaField(s, 6).toInt();   // 0=invalid, 1=GPS, 2=DGPS
  int    sats  = nmeaField(s, 7).toInt();
  float  alt   = nmeaField(s, 9).toFloat(); // metres

  if (latF.length() > 0 && lonF.length() > 0) {
    gps.lat   = nmeaToDecimal(latF, latH);
    gps.lon   = nmeaToDecimal(lonF, lonH);
    gps.alt   = alt;
    gps.fix   = (fix > 0) ? 1 : 0;
    gps.sats  = sats;
    gps.fresh = true;
  }
}

// Parse $GPRMC / $GNRMC → lat, lon, heading, validity
void parseRMC(const String& s) {
  if (!nmeaChecksum(s)) return;
  char   status = nmeaField(s, 2)[0];    // A=valid, V=invalid
  String latF   = nmeaField(s, 3);
  char   latH   = nmeaField(s, 4)[0];
  String lonF   = nmeaField(s, 5);
  char   lonH   = nmeaField(s, 6)[0];
  float  course = nmeaField(s, 8).toFloat();

  if (status == 'A' && latF.length() > 0) {
    gps.lat     = nmeaToDecimal(latF, latH);
    gps.lon     = nmeaToDecimal(lonF, lonH);
    gps.heading = course;
    gps.fix     = 1;
    gps.fresh   = true;
  }
}

// ─────────────────────────────────────────────────────────────
//  WEB GCS PAGE  (served at http://192.168.4.1/)
//  Full ground-control station in the phone browser — no laptop needed.
//  Telemetry polled via GET /api/telem (1s).
//  Commands sent via POST /api/cmd.
//  GPS streamed via POST /gps (existing endpoint).
//  Android Chrome needs a one-time flag for geolocation on plain HTTP:
//    chrome://flags/#unsafely-treat-insecure-origin-as-secure → add http://192.168.4.1
// ─────────────────────────────────────────────────────────────
static const char GCS_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#0d0d0d">
<title>SUDARSHAN GCS</title>
<style>
*{box-sizing:border-box}
body{background:#0d0d0d;color:#e0e0e0;font-family:Consolas,monospace;
     margin:0;padding:8px 8px 4px}
h2{color:#00e5ff;margin:0 0 5px;font-size:.9em;text-align:center;letter-spacing:2px}
.row{display:flex;gap:4px;margin-bottom:5px}
.card{background:#111;border:1px solid #1e1e1e;border-radius:3px;
      padding:4px 6px;flex:1;min-width:0}
.lbl{color:#444;font-size:.68em;text-transform:uppercase;white-space:nowrap}
.val{color:#00e676;font-size:.98em;font-weight:bold;white-space:nowrap;overflow:hidden}
#mb{background:#111;border:1px solid #1e1e1e;border-radius:3px;
    padding:5px 8px;margin-bottom:5px;display:flex;
    align-items:center;justify-content:space-between;font-size:.82em}
#mval{color:#00e5ff;font-weight:bold;letter-spacing:1px}
.btns{display:flex;gap:4px;margin-bottom:5px}
button{background:#0a0a0a;color:#00e5ff;border:1px solid #00e5ff;
       padding:9px 0;border-radius:3px;font-family:Consolas,monospace;
       font-size:.78em;cursor:pointer;flex:1;
       -webkit-tap-highlight-color:transparent;
       -webkit-user-select:none;user-select:none}
button:active{background:#00e5ff;color:#000}
#bkill{border-color:#ff3b3b;color:#ff3b3b}
#bkill.k2{background:#ff3b3b;color:#000;animation:bl .4s step-end infinite}
#barm{border-color:#00e676;color:#00e676}
#bdis{border-color:#ffcc00;color:#ffcc00}
@keyframes bl{0%,100%{opacity:1}50%{opacity:.15}}
#dms{text-align:center;font-size:.76em;color:#444;margin-bottom:5px}
#dmsc{font-size:1.1em;font-weight:bold;color:#00e676}
#dmsc.w{color:#ffcc00}#dmsc.c{color:#ff3b3b}
canvas{display:block;margin:0 auto 5px;border-radius:50%;border:1px solid #1e1e1e}
#ovr{display:none;background:#111;border:1px solid #1e1e1e;
     border-radius:3px;padding:6px;margin-bottom:5px}
#thrsldr{width:100%;accent-color:#00e5ff;margin-top:3px}
#gpsbtn{width:100%;background:#0a0a0a;color:#444;
        border:1px solid #222;padding:8px;border-radius:3px;
        font-family:Consolas,monospace;font-size:.78em;cursor:pointer;
        -webkit-tap-highlight-color:transparent}
#gpsbtn.on{color:#00e5ff;border-color:#00e5ff}
.tstep{padding:2px 0;border-bottom:1px solid #1a1a1a;color:#555;transition:color .3s}
input[type=number]{width:100%;background:#0a0a0a;color:#e0e0e0;border:1px solid #333;
  border-radius:3px;padding:4px 5px;font-family:Consolas,monospace;font-size:.78em;
  -webkit-appearance:none;appearance:none}
</style>
</head>
<body>
<h2>&#9650; SUDARSHAN GCS &#9650;</h2>

<div id="mb">
  <span id="mval">OFFLINE</span>
  <span id="armd" style="color:#444">DISARMED</span>
  <span id="live" style="color:#444">&#9679; OFFLINE</span>
</div>

<div class="row">
  <div class="card"><div class="lbl">ROLL</div><div class="val" id="troll">---</div></div>
  <div class="card"><div class="lbl">PITCH</div><div class="val" id="tpitch">---</div></div>
  <div class="card"><div class="lbl">YAW</div><div class="val" id="tyaw">---</div></div>
  <div class="card"><div class="lbl">ALT cm</div><div class="val" id="talt">---</div></div>
  <div class="card"><div class="lbl">BAT V</div><div class="val" id="tbat" style="color:#ffcc00">---</div></div>
</div>

<canvas id="ati" width="90" height="90"></canvas>

<div id="dms">DEAD-MAN: <span id="dmsc">--</span>s</div>

<div class="btns">
  <button id="barm"  onclick="sc('ARM')">ARM</button>
  <button id="bdis"  onclick="sc('DISARM')">DISARM</button>
  <button id="bhov"  onclick="sc('HOVER')">HOVER</button>
  <button id="blan"  onclick="sc('LAND')">LAND</button>
  <button id="bkill" onclick="kTap()">KILL</button>
</div>
<div class="btns">
  <button onclick="sc('PRESET',{id:1})">PST 1</button>
  <button onclick="sc('PRESET',{id:2})">PST 2</button>
  <button onclick="togOvr()">OVR&#9660;</button>
  <button onclick="togMT()">MOT&#9660;</button>
  <button onclick="togPF()">PF&#9660;</button>
</div>
<div class="btns">
  <button onclick="togNav()">NAV&#9660;</button>
  <button onclick="togTrn()">GUIDE&#9660;</button>
  <button onclick="togAlt()">ALT&#9660;</button>
  <button onclick="togPath()">PATH&#9660;</button>
</div>

<div id="ovr">
  <div class="lbl">THROTTLE <span id="thrv">1050</span> us</div>
  <input id="thrsldr" type="range" min="1050" max="1900" value="1050"
    oninput="document.getElementById('thrv').textContent=this.value"
    onchange="sc('OVERRIDE',{throttle:parseInt(this.value)})">
</div>

<div id="pfpanel" style="display:none;background:#111;border:1px solid #1e3030;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#00e5ff;letter-spacing:1px;margin-bottom:5px">PRE-FLIGHT CHECKLIST</div>
  <div style="width:100%;font-size:.82em;margin-bottom:5px">
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #1a1a1a"><span class="lbl">IMU (MPU6050)</span><span id="pfImu" style="font-weight:bold;color:#444">---</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #1a1a1a"><span class="lbl">SONAR / ALT</span><span id="pfSon" style="font-weight:bold;color:#444">---</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #1a1a1a"><span class="lbl">BATTERY</span><span id="pfBat" style="font-weight:bold;color:#444">---</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #1a1a1a"><span class="lbl">GPS / PHONE</span><span id="pfGps" style="font-weight:bold;color:#444">---</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0"><span class="lbl">MODE</span><span id="pfMod" style="font-weight:bold;color:#00e5ff">---</span></div>
  </div>
  <button id="gpsbtn2" style="width:100%;margin-bottom:6px;border-color:#00e5ff;color:#00e5ff;font-size:.75em" onclick="gpsStart()">&#9654; START PHONE GPS STREAMING</button>
  <div style="border-top:1px solid #2a1000;padding-top:5px">
    <div class="lbl" style="color:#ff9800;margin-bottom:3px">&#9888; ADMIN OVERRIDE — bypasses all pre-flight checks</div>
    <div id="pfAuthBox">
      <input id="pfPass" type="password" placeholder="Admin password"
        style="width:100%;background:#0a0a0a;color:#e0e0e0;border:1px solid #333;border-radius:3px;padding:5px 6px;font-family:Consolas,monospace;font-size:.8em;margin-bottom:4px;-webkit-appearance:none">
      <button style="width:100%;border-color:#ff9800;color:#ff9800" onclick="tryOverride()">UNLOCK FORCE ARM</button>
    </div>
    <button id="pfFarm" style="display:none;width:100%;border-color:#ff3b3b;color:#ff3b3b" onclick="sc('FORCE_ARM')">&#9889; FORCE ARM — ALL CHECKS BYPASSED</button>
  </div>
</div>
<div id="ackbar" style="display:none;background:#1a1a00;border:1px solid #ffcc00;border-radius:3px;padding:4px 6px;margin-bottom:5px;font-size:.75em;color:#ffcc00"></div>
<div id="mtest" style="display:none;background:#111;border:1px solid #332200;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#ff9800;margin-bottom:3px">&#9888; MOTOR TEST — REMOVE PROPS — DISARMED only</div>
  <div class="btns" style="margin:3px 0">
    <button id="mFL" onclick="mtSel('FL')">FL</button>
    <button id="mFR" onclick="mtSel('FR')">FR</button>
    <button id="mRL" onclick="mtSel('RL')">RL</button>
    <button id="mRR" onclick="mtSel('RR')">RR</button>
  </div>
  <div class="lbl">THR <span id="mtthrv">1100</span> us</div>
  <input id="mtthr" type="range" min="1050" max="1200" value="1100"
    style="width:100%;accent-color:#00e5ff;margin:2px 0 5px"
    oninput="document.getElementById('mtthrv').textContent=this.value">
  <div class="lbl">DURATION <span id="mtdurv">1500</span> ms</div>
  <input id="mtdur" type="range" min="500" max="2000" value="1500" step="100"
    style="width:100%;accent-color:#ffcc00;margin:2px 0 5px"
    oninput="document.getElementById('mtdurv').textContent=this.value">
  <button style="width:100%;border-color:#ffcc00;color:#ffcc00" onclick="sendMT()">&#9654; RUN TEST</button>
  <div style="border-top:1px solid #1a2a1a;margin-top:6px;padding-top:5px">
    <div class="lbl" style="color:#00e5ff;margin-bottom:2px">MOTOR IDENTIFICATION WIZARD</div>
    <div class="lbl" style="margin-bottom:4px">Spins each channel one at a time. Tell the GCS which physical motor moved — it will save the correct wiring map.</div>
    <div id="midStatus" style="font-size:.78em;color:#ffcc00;min-height:1.3em;margin:3px 0"></div>
    <div id="midPickBtns" class="btns" style="display:none;margin:4px 0">
      <button onclick="midPick('FL')">FL</button>
      <button onclick="midPick('FR')">FR</button>
      <button onclick="midPick('RL')">RL</button>
      <button onclick="midPick('RR')">RR</button>
    </div>
    <div id="midMapTxt" style="font-size:.75em;color:#00e676;min-height:1em;margin:3px 0"></div>
    <button id="midStartBtn" style="width:100%;border-color:#00e5ff;color:#00e5ff" onclick="midStart()">&#9654; START MOTOR IDENTIFICATION</button>
  </div>
  <div style="border-top:1px solid #222;margin-top:6px;padding-top:5px">
    <div class="lbl" style="color:#ff9800;margin-bottom:3px">&#9888; ESC CALIBRATION — props OFF — do once per ESC</div>
    <div class="lbl" style="margin-bottom:3px">Sends 2000µs → wait for double-beep → 1000µs → confirm beeps</div>
    <button style="width:100%;border-color:#ff9800;color:#ff9800" onclick="calEsc()">&#9889; CALIBRATE ALL ESCs</button>
  </div>
</div>
<div id="lockoverlay" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.85);z-index:99;align-items:center;justify-content:center">
  <div style="background:#111;border:1px solid #ff9800;border-radius:4px;padding:16px;max-width:280px;width:90%;text-align:center">
    <div class="lbl" style="color:#ff9800;font-size:.85em;margin-bottom:8px;letter-spacing:1px">&#9888; PYTHON GCS ACTIVE</div>
    <div class="lbl" style="margin-bottom:8px">Web GCS is locked while the laptop GCS is connected. Enter the priority code to override, or the master code for full access.</div>
    <input id="lockPass" type="password" placeholder="Priority or master code"
      style="width:100%;background:#0a0a0a;color:#e0e0e0;border:1px solid #555;border-radius:3px;padding:6px;font-family:Consolas,monospace;font-size:.82em;margin-bottom:8px;-webkit-appearance:none">
    <div id="lockMsg" style="font-size:.75em;color:#ff3b3b;min-height:1em;margin-bottom:6px"></div>
    <div class="btns" style="margin:0">
      <button style="border-color:#ff9800;color:#ff9800;flex:2" onclick="doUnlock()">UNLOCK</button>
      <button style="border-color:#555;color:#555;flex:1" onclick="hideLock()">CANCEL</button>
    </div>
  </div>
</div>

<div id="altpanel" style="display:none;background:#111;border:1px solid #0d1a20;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#00e5ff;letter-spacing:1px;margin-bottom:5px">ALTITUDE SETPOINT</div>
  <div class="lbl" style="margin-bottom:3px">TARGET <span id="altSV" style="color:#00e5ff">100</span> cm</div>
  <input id="altSldr" type="range" min="30" max="500" value="100" step="10"
    style="width:100%;accent-color:#00e5ff;margin-bottom:6px"
    oninput="document.getElementById('altSV').textContent=this.value">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <span class="lbl">CURRENT</span>
    <span id="altCur" style="color:#00e676;font-size:.9em;font-weight:bold">--- cm</span>
  </div>
  <button style="width:100%;border-color:#00e5ff;color:#00e5ff" onclick="setAlt()">SET ALTITUDE</button>
</div>

<div id="pathpanel" style="display:none;background:#111;border:1px solid #1a0d20;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#00e5ff;letter-spacing:1px;margin-bottom:5px">PATH BUILDER</div>
  <div class="lbl" style="margin-bottom:3px">Tap map to add waypoints. Scale: <span id="pathScaleV">2</span> m/px</div>
  <input type="range" min="1" max="10" value="2" step="1"
    style="width:100%;accent-color:#9c27b0;margin-bottom:4px"
    oninput="document.getElementById('pathScaleV').textContent=this.value" id="pathScale">
  <svg id="pathSvg" width="100%" viewBox="0 0 200 200"
    style="display:block;background:#0a0a0a;border:1px solid #222;border-radius:3px;margin-bottom:4px;touch-action:none"
    onclick="pathTap(event)" ontouchend="pathTouch(event)">
    <g id="pathGrid"></g>
    <g id="pathLines"></g>
    <g id="pathDots"></g>
  </svg>
  <div id="pathInfo" style="font-size:.75em;color:#ffcc00;min-height:1.2em;margin-bottom:4px;text-align:center">Tap map to start</div>
  <div class="btns">
    <button style="border-color:#00e676;color:#00e676;flex:2" onclick="pathExec()">&#10148; EXECUTE PATH</button>
    <button style="border-color:#ff3b3b;color:#ff3b3b;flex:1" onclick="pathClear()">CLEAR</button>
  </div>
</div>

<div id="navpanel" style="display:none;background:#111;border:1px solid #0d2020;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#00e5ff;letter-spacing:1px;margin-bottom:5px">GPS NAVIGATION</div>
  <svg id="navSvg" width="110" height="110" style="display:block;margin:0 auto 5px">
    <circle cx="55" cy="55" r="52" fill="#0d0d0d" stroke="#222" stroke-width="1"/>
    <text x="55" y="13" fill="#00e5ff" font-size="9" text-anchor="middle" font-family="Consolas,monospace">N</text>
    <text x="55" y="105" fill="#555" font-size="9" text-anchor="middle" font-family="Consolas,monospace">S</text>
    <text x="8" y="59" fill="#555" font-size="9" text-anchor="middle" font-family="Consolas,monospace">W</text>
    <text x="103" y="59" fill="#555" font-size="9" text-anchor="middle" font-family="Consolas,monospace">E</text>
    <line id="navBrgLine" x1="55" y1="55" x2="55" y2="8" stroke="#00e676" stroke-width="2" stroke-dasharray="5,3" opacity="0"/>
    <line id="navHdgLine" x1="55" y1="55" x2="55" y2="8" stroke="#ff3b3b" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="55" cy="55" r="3" fill="#e0e0e0"/>
  </svg>
  <div style="display:flex;gap:4px;margin-bottom:4px">
    <div style="flex:1"><div class="lbl">TARGET LAT</div>
      <input id="navLat" type="number" step="0.000001" placeholder="0.000000"></div>
    <div style="flex:1"><div class="lbl">TARGET LON</div>
      <input id="navLon" type="number" step="0.000001" placeholder="0.000000"></div>
  </div>
  <button style="width:100%;border-color:#00e5ff;color:#00e5ff;margin-bottom:3px;font-size:.75em" onclick="navUsePhone()">&#9654; USE PHONE GPS AS TARGET</button>
  <div id="navInfo" style="font-size:.78em;color:#ffcc00;min-height:1.3em;margin:3px 0;text-align:center">-- Set target coordinates --</div>
  <div style="margin-bottom:4px">
    <div class="lbl">SPEED <span id="navSpdV">2</span> m/s</div>
    <input type="range" min="1" max="8" value="2" style="width:100%;accent-color:#00e5ff" oninput="document.getElementById('navSpdV').textContent=this.value" id="navSpd">
  </div>
  <div class="btns">
    <button style="border-color:#00e676;color:#00e676;flex:2" onclick="navFlyTo()">&#10148; FLY TO</button>
    <button style="border-color:#ffcc00;color:#ffcc00;flex:1" onclick="navCalc()">CALC</button>
    <button style="border-color:#ff9800;color:#ff9800;flex:1" onclick="sc('PRESET',{id:'RTL'})">RTL</button>
  </div>
</div>

<div id="trnpanel" style="display:none;background:#111;border:1px solid #142010;border-radius:3px;padding:6px;margin-bottom:5px">
  <div class="lbl" style="color:#00e676;letter-spacing:1px;margin-bottom:5px">TRAINING GUIDE</div>
  <div class="lbl" style="margin-bottom:3px">LIVE PRE-FLIGHT CHECKLIST</div>
  <div id="trnStep0" class="tstep">&#9744; Power on — waiting for FC connection</div>
  <div id="trnStep1" class="tstep">&#9744; IMU calibrated and healthy</div>
  <div id="trnStep2" class="tstep">&#9744; Sonar active and reading altitude</div>
  <div id="trnStep3" class="tstep">&#9744; Battery above 10.5V</div>
  <div id="trnStep4" class="tstep">&#9744; Phone GPS fix obtained</div>
  <div id="trnStep5" class="tstep">&#9744; Drone stable — roll/pitch within &#177;5&#176;</div>
  <div id="trnStep6" class="tstep" style="border-bottom:none">&#9744; ARM the drone</div>
  <div style="border-top:1px solid #1a2a1a;margin-top:5px;padding-top:5px">
    <div class="lbl" style="color:#ff9800;margin-bottom:2px">SIMULATION LOCK</div>
    <div class="lbl" style="margin-bottom:3px">Blocks ARM — safe for UI familiarization and training.</div>
    <button id="simBtn" style="width:100%;border-color:#00e676;color:#00e676;margin-bottom:3px" onclick="togSim()">&#9632; ENABLE SIM LOCK</button>
    <div id="simInd" style="display:none;text-align:center;color:#ff9800;font-size:.78em;padding:3px 0;letter-spacing:1px">&#9888; SIM MODE — ARM BLOCKED</div>
  </div>
</div>

<div class="row">
  <div class="card"><div class="lbl">LAT</div><div id="glat" class="val" style="color:#ccc">---</div></div>
  <div class="card"><div class="lbl">LON</div><div id="glon" class="val" style="color:#ccc">---</div></div>
  <div class="card"><div class="lbl">FIX/SAT</div><div id="gfix" class="val" style="color:#ccc">---</div></div>
</div>

<button id="gpsbtn" onclick="gpsStart()">&#9654; START GPS STREAMING</button>

<script>
var dV=30,kAr=false,kTm=0,gW=0;
var cv=document.getElementById('ati'),cx=cv.getContext('2d');
var W=90,H=90,MX=45,MY=45,R=43;

function drawAti(r,p){
  cx.clearRect(0,0,W,H);
  cx.save();
  cx.beginPath();cx.arc(MX,MY,R,0,2*Math.PI);cx.clip();
  cx.save();cx.translate(MX,MY);cx.rotate(-r*Math.PI/180);
  var ry=p*1.5;
  cx.fillStyle='#0d2a42';cx.fillRect(-R,-R*2-ry,R*2,R*2);
  cx.fillStyle='#2a1400';cx.fillRect(-R,-ry,R*2,R*2);
  cx.restore();
  cx.beginPath();cx.arc(MX,MY,R,0,2*Math.PI);
  cx.strokeStyle='#333';cx.lineWidth=1;cx.stroke();
  cx.strokeStyle='rgba(255,255,255,.7)';cx.lineWidth=1.5;
  cx.beginPath();cx.moveTo(MX-25,MY);cx.lineTo(MX-8,MY);cx.stroke();
  cx.beginPath();cx.moveTo(MX+8,MY);cx.lineTo(MX+25,MY);cx.stroke();
  cx.beginPath();cx.moveTo(MX,MY-4);cx.lineTo(MX,MY+4);cx.stroke();
  cx.restore();
}
drawAti(0,0);

function setDms(v){
  dV=v;
  var e=document.getElementById('dmsc');
  e.textContent=v;
  e.className=v<=8?'c':v<=15?'w':'';
}
setInterval(function(){if(dV>0)setDms(dV-1);},1000);

function sc(cmd,extra){
  if(simLock&&cmd==='ARM'){
    var ab=document.getElementById('ackbar');
    ab.style.display='block';ab.textContent='&#9888; SIM MODE — ARM BLOCKED';
    clearTimeout(window._ackTm);window._ackTm=setTimeout(function(){ab.style.display='none';},3000);
    return;
  }
  setDms(30);
  var b={cmd:cmd};
  if(extra){for(var k in extra)b[k]=extra[k];}
  fetch('/api/cmd',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(b)})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.locked){showLock(cmd,extra);}
    }).catch(function(){});
}

setInterval(function(){sc('PING');},25000);

function kTap(){
  var b=document.getElementById('bkill');
  if(!kAr){
    kAr=true;b.classList.add('k2');b.textContent='CONFIRM';
    clearTimeout(kTm);
    kTm=setTimeout(function(){kAr=false;b.classList.remove('k2');b.textContent='KILL';},3000);
  } else {
    clearTimeout(kTm);kAr=false;b.classList.remove('k2');b.textContent='KILL';
    sc('KILL');
  }
}

function togOvr(){
  var d=document.getElementById('ovr');
  d.style.display=(d.style.display==='block')?'none':'block';
}

function applyTelem(d){
  var lv=document.getElementById('live');
  lv.textContent='● LIVE';lv.style.color='#00e676';
  document.getElementById('mval').textContent=(d.mode||'---');
  var ae=document.getElementById('armd');
  if(d.armed){ae.textContent='ARMED';ae.style.color='#00e676';}
  else{ae.textContent='DISARMED';ae.style.color='#444';}
  var f=function(v,n){return(typeof v==='number')?v.toFixed(n===undefined?1:n):'---';};
  document.getElementById('troll').textContent=f(d.roll)+'*';
  document.getElementById('tpitch').textContent=f(d.pitch)+'*';
  document.getElementById('tyaw').textContent=f(d.yaw)+'*';
  document.getElementById('talt').textContent=typeof d.alt_cm==='number'?d.alt_cm+'cm':'---';
  document.getElementById('tbat').textContent=typeof d.bat_mv==='number'?(d.bat_mv/1000).toFixed(2)+'V':'---';
  document.getElementById('altCur').textContent=(typeof d.alt_cm==='number'?d.alt_cm:'---')+' cm';
  if(d.last_ack){try{var a=JSON.parse(d.last_ack);var ab=document.getElementById('ackbar');ab.style.display='block';ab.textContent='FC: '+a.ack+' '+a.status+(a.msg?' — '+a.msg:'');clearTimeout(window._ackTm);window._ackTm=setTimeout(function(){ab.style.display='none';},6000);}catch(e){}}
  var _G='#00e676',_R='#ff3b3b',_Y='#ffcc00',_U='#444';
  if(typeof d.imu_ok==='number'){var ie=document.getElementById('pfImu');ie.textContent=d.imu_ok?'PASS':'FAIL';ie.style.color=d.imu_ok?_G:_R;}
  if(typeof d.sonar_ok==='number'){var se=document.getElementById('pfSon');se.textContent=d.sonar_ok?'PASS':'STALE';se.style.color=d.sonar_ok?_G:_Y;}
  if(typeof d.bat_mv==='number'&&d.bat_mv>0){var bv=d.bat_mv/1000,be=document.getElementById('pfBat');be.textContent=bv.toFixed(2)+'V'+(d.bat_mv<9900?' CRITICAL':d.bat_mv<10500?' LOW':'');be.style.color=d.bat_mv>10500?_G:d.bat_mv>9900?_Y:_R;}
  var ge=document.getElementById('pfGps');if(d.gps_fix){ge.textContent='FIX ('+d.gps_sats+' sat)';ge.style.color=_G;}else{ge.textContent='NO FIX — press GPS button';ge.style.color=_U;}
  var me=document.getElementById('pfMod');if(me)me.textContent=d.mode||'---';
  if(typeof d.roll==='number')drawAti(d.roll||0,d.pitch||0);
  if(d.gps_lat&&d.gps_lat!==0){
    document.getElementById('glat').textContent=d.gps_lat.toFixed(6);
    document.getElementById('glon').textContent=d.gps_lon.toFixed(6);
    document.getElementById('gfix').textContent=(d.gps_fix?'FIX':'---')+'/'+(d.gps_sats||0);
    navPhoneLat=d.gps_lat;navPhoneLon=d.gps_lon;
  }
  window._lastHdg=typeof d.yaw==='number'?d.yaw:0;
  navUpdateSvg(window._lastHdg,null);
  navUpdateTrn(d);
  // Priority lock indicator
  if(d.gcs_lock){
    var li=document.getElementById('live');
    li.textContent='● LOCKED';li.style.color='#ff9800';
  }
}
function pollTelem(){
  if(window._wsOk)return;
  fetch('/api/telem').then(function(r){return r.json();}).then(function(d){
    applyTelem(d);
  }).catch(function(){
    var lv=document.getElementById('live');
    lv.textContent='● OFFLINE';lv.style.color='#444';
  });
}
setInterval(pollTelem,1000);
pollTelem();

// WebSocket for real-time push (no polling lag when WS is up)
window._wsOk=false;
function connectWS(){
  try{
    var ws=new WebSocket('ws://'+location.hostname+':81/');
    ws.onopen=function(){window._wsOk=true;};
    ws.onmessage=function(e){try{applyTelem(JSON.parse(e.data));}catch(_){}};
    ws.onclose=ws.onerror=function(){window._wsOk=false;ws=null;setTimeout(connectWS,3000);};
  }catch(_){window._wsOk=false;setTimeout(connectWS,5000);}
}
connectWS();

var mtMot='FL';
function mtSel(m){
  ['FL','FR','RL','RR'].forEach(function(x){
    var b=document.getElementById('m'+x);
    b.style.background=(x===m)?'#00e5ff':'';
    b.style.color=(x===m)?'#000':'#00e5ff';
  });
  mtMot=m;
}
function togMT(){
  var d=document.getElementById('mtest');
  d.style.display=(d.style.display==='block')?'none':'block';
}
function sendMT(){
  sc('MOTOR_TEST',{motor:mtMot,
    throttle:parseInt(document.getElementById('mtthr').value),
    duration_ms:parseInt(document.getElementById('mtdur').value)});
}
function calEsc(){sc('CAL_ESC');}
mtSel('FL');

var midCh=0,midMapR={},midUsed=[];
function midStart(){
  midCh=0;midMapR={};midUsed=[];
  document.getElementById('midStartBtn').style.display='none';
  document.getElementById('midMapTxt').textContent='';
  document.getElementById('midPickBtns').style.display='none';
  midDoChannel();
}
function midDoChannel(){
  if(midCh>3){
    sc('SET_MOTOR_MAP',midMapR);
    var t='Map saved: ';
    ['fl','fr','rl','rr'].forEach(function(k){t+=k.toUpperCase()+'->CH'+midMapR[k]+' ';});
    document.getElementById('midStatus').textContent=t;
    document.getElementById('midPickBtns').style.display='none';
    var sb=document.getElementById('midStartBtn');
    sb.style.display='block';sb.textContent='&#9654; RE-RUN IDENTIFICATION';
    return;
  }
  document.getElementById('midStatus').textContent='Spinning CH'+midCh+'... which motor just moved?';
  fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cmd:'SPIN_CH',ch:midCh,thr:1100,dur:2000})}).catch(function(){});
  setTimeout(function(){document.getElementById('midPickBtns').style.display='flex';},400);
}
function midPick(m){
  var mk=m.toLowerCase();
  if(midUsed.indexOf(mk)>=0){
    document.getElementById('midStatus').textContent=m+' already assigned — pick another!';
    return;
  }
  document.getElementById('midPickBtns').style.display='none';
  midMapR[mk]=midCh;midUsed.push(mk);
  var t='';['fl','fr','rl','rr'].forEach(function(k){if(midMapR[k]!==undefined)t+=k.toUpperCase()+'->CH'+midMapR[k]+'  ';});
  document.getElementById('midMapTxt').textContent=t;
  midCh++;
  document.getElementById('midStatus').textContent='Got it. Next channel in 2.5s...';
  setTimeout(midDoChannel,2500);
}

function togPF(){
  var d=document.getElementById('pfpanel');
  d.style.display=(d.style.display==='block')?'none':'block';
}

// ── NAV panel ──
var navPhoneLat=0,navPhoneLon=0,simLock=false;
function haversine(a,b,c,d){
  var R=6371000,dL=(c-a)*Math.PI/180,dN=(d-b)*Math.PI/180;
  var s=Math.sin(dL/2)*Math.sin(dL/2)+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(dN/2)*Math.sin(dN/2);
  return R*2*Math.atan2(Math.sqrt(s),Math.sqrt(1-s));
}
function calcBrg(a,b,c,d){
  var dN=(d-b)*Math.PI/180;
  var y=Math.sin(dN)*Math.cos(c*Math.PI/180);
  var x=Math.cos(a*Math.PI/180)*Math.sin(c*Math.PI/180)-Math.sin(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.cos(dN);
  return(Math.atan2(y,x)*180/Math.PI+360)%360;
}
function navUpdateSvg(hdg,brg){
  var r=46,cx=55,cy=55;
  function pt(a){return{x:cx+r*Math.sin(a*Math.PI/180),y:cy-r*Math.cos(a*Math.PI/180)};}
  var h=document.getElementById('navHdgLine'),p=pt(hdg||0);
  h.setAttribute('x2',p.x);h.setAttribute('y2',p.y);
  var bl=document.getElementById('navBrgLine');
  if(brg!==null&&brg!==undefined){var pb=pt(brg);bl.setAttribute('x2',pb.x);bl.setAttribute('y2',pb.y);bl.setAttribute('opacity','1');}
  else{bl.setAttribute('opacity','0');}
}
function navCalc(){
  var la=parseFloat(document.getElementById('navLat').value);
  var lo=parseFloat(document.getElementById('navLon').value);
  if(isNaN(la)||isNaN(lo)){document.getElementById('navInfo').textContent='Enter valid coordinates';return;}
  var dist=haversine(navPhoneLat||0,navPhoneLon||0,la,lo);
  var brg=calcBrg(navPhoneLat||0,navPhoneLon||0,la,lo);
  navUpdateSvg(window._lastHdg||0,brg);
  document.getElementById('navInfo').textContent='BRG: '+brg.toFixed(1)+'&#176; | DIST: '+(dist<1000?dist.toFixed(0)+'m':(dist/1000).toFixed(2)+'km');
}
function navUsePhone(){
  if(!navPhoneLat){document.getElementById('navInfo').textContent='No phone GPS fix yet — press START GPS';return;}
  document.getElementById('navLat').value=navPhoneLat.toFixed(6);
  document.getElementById('navLon').value=navPhoneLon.toFixed(6);
  document.getElementById('navInfo').textContent='Target set to current phone position';
}
function navFlyTo(){
  var la=parseFloat(document.getElementById('navLat').value);
  var lo=parseFloat(document.getElementById('navLon').value);
  if(isNaN(la)||isNaN(lo)){document.getElementById('navInfo').textContent='Set a target first';return;}
  var spd=parseFloat(document.getElementById('navSpd').value)||2;
  var brg=calcBrg(navPhoneLat||0,navPhoneLon||0,la,lo);
  var dist=haversine(navPhoneLat||0,navPhoneLon||0,la,lo);
  sc('PRESET',{id:'NAV',bear:parseFloat(brg.toFixed(1)),dist:parseFloat(dist.toFixed(0)),speed:spd});
  document.getElementById('navInfo').textContent='Sent: BRG '+brg.toFixed(1)+'&#176; | '+dist.toFixed(0)+'m @ '+spd+'m/s';
}
function togNav(){
  var d=document.getElementById('navpanel');
  d.style.display=(d.style.display==='block')?'none':'block';
}

// ── Training / Guide panel ──
function togSim(){
  simLock=!simLock;
  var b=document.getElementById('simBtn');
  var i=document.getElementById('simInd');
  if(simLock){b.textContent='&#9658; DISABLE SIM LOCK';b.style.borderColor='#ff9800';b.style.color='#ff9800';i.style.display='block';}
  else{b.textContent='&#9632; ENABLE SIM LOCK';b.style.borderColor='#00e676';b.style.color='#00e676';i.style.display='none';}
}
function togTrn(){
  var d=document.getElementById('trnpanel');
  d.style.display=(d.style.display==='block')?'none':'block';
}
function navUpdateTrn(d){
  var steps=[
    ['trnStep0',d.mode&&d.mode!=='DISCONNECTED'],
    ['trnStep1',d.imu_ok===1],
    ['trnStep2',d.sonar_ok===1],
    ['trnStep3',!!(d.bat_mv&&d.bat_mv>=10500)],
    ['trnStep4',!!(d.gps_fix&&d.gps_fix>0)],
    ['trnStep5',typeof d.roll==='number'&&Math.abs(d.roll)<5&&typeof d.pitch==='number'&&Math.abs(d.pitch)<5],
    ['trnStep6',d.armed===1]
  ];
  steps.forEach(function(s){
    var e=document.getElementById(s[0]);if(!e)return;
    var txt=e.textContent.slice(2);
    e.textContent=(s[1]?'☑ ':'❄ ')+txt;
    e.style.color=s[1]?'#00e676':'#555';
  });
}
function tryOverride(){
  var p=document.getElementById('pfPass').value;
  if(!p)return;
  fetch('/api/auth',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({pass:p})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.ok){
      document.getElementById('pfAuthBox').style.display='none';
      document.getElementById('pfFarm').style.display='block';
    } else {
      var inp=document.getElementById('pfPass');
      inp.style.borderColor='#ff3b3b';
      inp.value='';
      setTimeout(function(){inp.style.borderColor='#333';},1200);
    }
  }).catch(function(){});
}

// ── Priority lock prompt ──
var _pendCmd=null,_pendExtra=null;
function showLock(cmd,extra){_pendCmd=cmd;_pendExtra=extra;document.getElementById('lockoverlay').style.display='flex';document.getElementById('lockPass').value='';document.getElementById('lockMsg').textContent='';}
function hideLock(){document.getElementById('lockoverlay').style.display='none';}
function doUnlock(){
  var p=document.getElementById('lockPass').value;
  if(!p)return;
  fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pass:p})})
    .then(function(r){return r.json();}).then(function(d){
      if(d.ok){hideLock();if(_pendCmd)sc(_pendCmd,_pendExtra);}
      else{var m=document.getElementById('lockMsg');m.textContent='Wrong code';setTimeout(function(){m.textContent='';},2000);}
    }).catch(function(){});
}

// ── Alt setpoint panel ──
function togAlt(){var d=document.getElementById('altpanel');d.style.display=(d.style.display==='block')?'none':'block';}
function setAlt(){sc('ALT_HOLD',{alt_cm:parseInt(document.getElementById('altSldr').value)});}

// ── Path builder ──
var pathWps=[{x:100,y:100}];
function pathDraw(){
  var svg=document.getElementById('pathSvg');
  var grid=document.getElementById('pathGrid');
  var lines=document.getElementById('pathLines');
  var dots=document.getElementById('pathDots');
  grid.innerHTML='';lines.innerHTML='';dots.innerHTML='';
  for(var x=0;x<=200;x+=20){grid.innerHTML+='<line x1="'+x+'" y1="0" x2="'+x+'" y2="200" stroke="#151515" stroke-width="0.5"/>';}
  for(var y=0;y<=200;y+=20){grid.innerHTML+='<line x1="0" y1="'+y+'" x2="200" y2="'+y+'" stroke="#151515" stroke-width="0.5"/>';}
  for(var i=1;i<pathWps.length;i++){
    var a=pathWps[i-1],b=pathWps[i];
    lines.innerHTML+='<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'" stroke="#00e5ff" stroke-width="1.5" marker-end="url(#arr)"/>';
  }
  for(var i=0;i<pathWps.length;i++){
    var col=i===0?'#00e676':i===pathWps.length-1?'#ff3b3b':'#ffcc00';
    dots.innerHTML+='<circle cx="'+pathWps[i].x+'" cy="'+pathWps[i].y+'" r="4" fill="'+col+'"/><text x="'+(pathWps[i].x+6)+'" y="'+(pathWps[i].y+4)+'" fill="'+col+'" font-size="7" font-family="Consolas,monospace">'+i+'</text>';
  }
  var sc=parseInt(document.getElementById('pathScale').value)||2;
  var segs=pathSegs();
  var tot=segs.reduce(function(a,s){return a+s.dist_m;},0);
  document.getElementById('pathInfo').textContent=segs.length>0?(pathWps.length-1)+' waypoints | '+tot.toFixed(0)+'m total':'Tap map to start';
}
function pathSvgCoords(e){
  var el=document.getElementById('pathSvg');
  var rect=el.getBoundingClientRect();
  var scX=200/rect.width,scY=200/rect.height;
  return{x:Math.round((e.clientX-rect.left)*scX),y:Math.round((e.clientY-rect.top)*scY)};
}
function pathTap(e){var p=pathSvgCoords(e);pathWps.push(p);pathDraw();}
function pathTouch(e){e.preventDefault();if(e.changedTouches.length){var t=e.changedTouches[0];var p=pathSvgCoords(t);pathWps.push(p);pathDraw();}}
function pathSegs(){
  var sc=parseInt(document.getElementById('pathScale').value)||2;
  var segs=[];
  for(var i=1;i<pathWps.length;i++){
    var dx=(pathWps[i].x-pathWps[i-1].x)*sc;
    var dy=-(pathWps[i].y-pathWps[i-1].y)*sc;
    var dist=Math.sqrt(dx*dx+dy*dy);
    var bear=((Math.atan2(dx,dy)*180/Math.PI)+360)%360;
    segs.push({bearing:parseFloat(bear.toFixed(1)),dist_m:parseFloat(dist.toFixed(1)),speed:0.5});
  }
  return segs;
}
function pathExec(){
  var segs=pathSegs();
  if(!segs.length){document.getElementById('pathInfo').textContent='Add at least 1 waypoint first';return;}
  sc('PRESET',{segments:segs});
  document.getElementById('pathInfo').textContent='Sent '+segs.length+' segment(s) to FC';
}
function pathClear(){pathWps=[{x:100,y:100}];pathDraw();}
function togPath(){
  var d=document.getElementById('pathpanel');
  var show=d.style.display!=='block';
  d.style.display=show?'block':'none';
  if(show)pathDraw();
}
pathDraw();

function gpsStart(){
  var btn=document.getElementById('gpsbtn');
  if(!navigator.geolocation){
    btn.textContent='Geolocation not supported';return;
  }
  btn.textContent='Requesting GPS...';
  if(gW)navigator.geolocation.clearWatch(gW);
  gW=navigator.geolocation.watchPosition(function(p){
    var c=p.coords;
    btn.textContent='● GPS STREAMING ('+c.accuracy.toFixed(0)+'m)';
    btn.classList.add('on');
    navPhoneLat=c.latitude;navPhoneLon=c.longitude;
    fetch('/gps',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lat:c.latitude,lon:c.longitude,
        alt:c.altitude||0,heading:c.heading||0,acc:c.accuracy})
    }).catch(function(){});
  },function(e){
    btn.classList.remove('on');
    var hint=(e.code===1)?' | Chrome fix: flags unsafely-treat-insecure-origin-as-secure':'';
    btn.textContent=(e.message||'GPS error')+hint;
  },{enableHighAccuracy:true,maximumAge:0,timeout:10000});
}
</script>
</body></html>
)rawliteral";

// ─────────────────────────────────────────────────────────────
//  GLOBALS
// ─────────────────────────────────────────────────────────────
WebServer  httpServer(80);
WiFiServer gcsServer(PORT_GCS);
WiFiServer phoneServer(PORT_PHONE);
WiFiClient gcsClient;
WiFiClient phoneClient;

String bufFC    = "";
String bufGCS   = "";
String bufPhone = "";

unsigned long lastPing     = 0;
unsigned long lastGpsFwd   = 0;
bool          dmsArmed     = false;
bool          dmsFired     = false;
bool          phoneWasConn = false;

String lastTelemJson = "";   // latest FC telemetry JSON — served to web GCS
String lastAckJson   = "";   // latest FC ACK JSON — piggybacked on /api/telem

WebSocketsServer wsServer(81);   // WS port 81 — push telem to phone browser

bool webGcsLocked   = false;   // true when Python GCS is connected on TCP
bool webGcsUnlocked = false;   // true after priority/master code entered
bool gcsPrevConn    = false;   // edge-detect for GCS connect/disconnect

// ─────────────────────────────────────────────────────────────
//  HTTP WEB GCS  (full GCS in phone browser — no laptop required)
// ─────────────────────────────────────────────────────────────
void handleRoot() {
  httpServer.send_P(200, "text/html", GCS_PAGE);
}

// Build merged telem JSON (telem + GPS + lock state) — used by HTTP and WS
String buildMergedTelem() {
  if (lastTelemJson.length() == 0)
    return F("{\"mode\":\"DISCONNECTED\",\"armed\":0}");
  StaticJsonDocument<512> doc;
  deserializeJson(doc, lastTelemJson);
  doc["gps_lat"]  = gps.lat;
  doc["gps_lon"]  = gps.lon;
  doc["gps_fix"]  = gps.fix;
  doc["gps_sats"] = gps.sats;
  doc["gps_hdg"]  = gps.heading;
  doc["dms_ok"]   = !dmsFired;
  doc["gcs_lock"] = (webGcsLocked && !webGcsUnlocked) ? 1 : 0;
  String out;
  serializeJson(doc, out);
  return out;
}

// GET /api/telem — returns last FC telemetry merged with GPS and ESP32 state
void handleWebTelem() {
  String body = buildMergedTelem();
  if (lastAckJson.length() > 0) {
    StaticJsonDocument<512> doc;
    deserializeJson(doc, body);
    doc["last_ack"] = lastAckJson;
    lastAckJson = "";
    body = "";
    serializeJson(doc, body);
  }
  httpServer.send(200, "application/json", body);
}

// POST /api/cmd — forwards command JSON to FC, resets ESP32 DMS
void handleWebCmd() {
  if (!httpServer.hasArg("plain")) { httpServer.send(400); return; }
  // Priority lock: block web GCS commands when Python GCS is on TCP unless unlocked
  if (webGcsLocked && !webGcsUnlocked) {
    httpServer.send(200, "application/json",
      "{\"ok\":0,\"locked\":1,\"reason\":\"Python GCS active — enter priority code\"}");
    return;
  }
  String body = httpServer.arg("plain");
  lastPing = millis();
  dmsFired = false;
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, body) == DeserializationError::Ok) {
    const char* cmd = doc["cmd"];
    if (cmd) {
      Serial.printf("[WEB→FC] %s\n", cmd);
      sendToFC(body);
    }
  }
  httpServer.send(200, "application/json", "{\"ok\":1}");
}

void handleGpsPost() {
  if (!httpServer.hasArg("plain")) { httpServer.send(400); return; }
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, httpServer.arg("plain")) != DeserializationError::Ok) {
    httpServer.send(400); return;
  }
  gps.lat     = doc["lat"]     | (double)0.0;
  gps.lon     = doc["lon"]     | (double)0.0;
  gps.alt     = doc["alt"]     | 0.0f;
  gps.heading = doc["heading"] | 0.0f;
  float acc   = doc["acc"]     | 999.0f;
  gps.fix     = (acc < 100.0f) ? 1 : 0;  // browser API has no fix-type field
  gps.sats    = 0;                         // not available from browser API
  gps.fresh   = true;
  httpServer.send(200, "application/json", "{\"ok\":1}");
  Serial.printf("[HTTP ] GPS  lat=%.6f  lon=%.6f  acc=%.0fm  fix=%d\n",
                gps.lat, gps.lon, acc, gps.fix);
}

void handleStatus() {
  bool gcsConn = (gcsClient && gcsClient.connected());
  String body = "{\"gcs\":" + String(gcsConn ? 1 : 0) +
                ",\"fix\":" + String(gps.fix) + "}";
  httpServer.send(200, "application/json", body);
}

void handleAuth() {
  if (!httpServer.hasArg("plain")) { httpServer.send(400); return; }
  StaticJsonDocument<64> req;
  if (deserializeJson(req, httpServer.arg("plain")) != DeserializationError::Ok) {
    httpServer.send(400); return;
  }
  const char* p = req["pass"] | "";
  bool ok = (strcmp(p, ADMIN_PASS) == 0 || strcmp(p, MASTER_PASS) == 0);
  httpServer.send(200, "application/json", ok ? "{\"ok\":1}" : "{\"ok\":0}");
}

// POST /api/unlock — accepts priority or master code to override priority lock
void handleUnlock() {
  if (!httpServer.hasArg("plain")) { httpServer.send(400); return; }
  StaticJsonDocument<64> req;
  if (deserializeJson(req, httpServer.arg("plain")) != DeserializationError::Ok) {
    httpServer.send(400); return;
  }
  const char* p = req["pass"] | "";
  bool ok = (strcmp(p, PRIORITY_PASS) == 0 || strcmp(p, MASTER_PASS) == 0);
  if (ok) webGcsUnlocked = true;
  httpServer.send(200, "application/json", ok ? "{\"ok\":1}" : "{\"ok\":0}");
}

void setupHTTP() {
  httpServer.on("/",           HTTP_GET,  handleRoot);
  httpServer.on("/api/telem",  HTTP_GET,  handleWebTelem);
  httpServer.on("/api/cmd",    HTTP_POST, handleWebCmd);
  httpServer.on("/gps",        HTTP_POST, handleGpsPost);
  httpServer.on("/status",     HTTP_GET,  handleStatus);
  httpServer.on("/api/auth",   HTTP_POST, handleAuth);
  httpServer.on("/api/unlock", HTTP_POST, handleUnlock);
  httpServer.begin();
  wsServer.begin();
  wsServer.onEvent([](uint8_t, WStype_t, uint8_t*, size_t){});
  Serial.println("[HTTP ] Web GCS http://192.168.4.1/  WS ws://192.168.4.1:81/");
}

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  initCrypto();
  Serial.printf("[CRYPTO] AES-128-CBC %s\n",
                ENCRYPT_ENABLED ? "ENABLED" : "DISABLED (plaintext)");

  Serial2.begin(FC_BAUD, SERIAL_8N1, FC_RX_PIN, FC_TX_PIN);
  Serial.println("[UART ] Serial2 up @ 115200  RX=" +
                 String(FC_RX_PIN) + "  TX=" + String(FC_TX_PIN));

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GW, AP_SN);
  bool ok = WiFi.softAP(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi ] AP %s  SSID: %s  IP: %s\n",
                ok ? "OK" : "FAIL", WIFI_SSID,
                WiFi.softAPIP().toString().c_str());

  gcsServer.begin();
  phoneServer.begin();
  Serial.printf("[TCP  ] GCS:%d  Phone:%d (NMEA — GPS Server by Metrologic, TCP CLIENT mode)\n",
                PORT_GCS, PORT_PHONE);
  setupHTTP();

  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH); delay(80);
    digitalWrite(LED_PIN, LOW);  delay(80);
  }
  Serial.println("[READY] Waiting for GCS...");
}

// ─────────────────────────────────────────────────────────────
//  LOOP
// ─────────────────────────────────────────────────────────────
void loop() {
  httpServer.handleClient();
  wsServer.loop();
  acceptClients();
  readGCS();
  readPhone();
  readFC();
  checkDMS();
  forwardGPS();
  statusLED();
}

// ─────────────────────────────────────────────────────────────
//  CLIENT ACCEPT
// ─────────────────────────────────────────────────────────────
void acceptClients() {
  bool gcsNowConn = (gcsClient && gcsClient.connected());
  if (!gcsNowConn && gcsPrevConn) {
    // Python GCS just disconnected — release priority lock
    webGcsLocked   = false;
    webGcsUnlocked = false;
    Serial.println("[GCS  ] Disconnected — web GCS lock released");
  }
  if (!gcsNowConn) {
    WiFiClient c = gcsServer.available();
    if (c) {
      if (gcsClient) gcsClient.stop();
      gcsClient = c;
      gcsClient.setNoDelay(true);
      bufGCS   = "";
      lastPing = millis();
      dmsArmed = true;
      dmsFired = false;
      // Python GCS connected — lock web GCS (force priority code to override)
      webGcsLocked   = true;
      webGcsUnlocked = false;
      gcsNowConn = true;
      Serial.printf("[GCS  ] Connected from %s — web GCS locked\n",
                    gcsClient.remoteIP().toString().c_str());
      sendToGCS("{\"info\":\"GCS_CONNECTED\"}");
    }
  }
  gcsPrevConn = gcsNowConn;

  bool phoneNowConn = (phoneClient && phoneClient.connected());
  if (phoneWasConn && !phoneNowConn) {
    sendToGCS("{\"info\":\"PHONE_DISCONNECTED\"}");
    Serial.println("[PHONE] Disconnected");
  }
  phoneWasConn = phoneNowConn;

  if (!phoneNowConn) {
    WiFiClient c = phoneServer.available();
    if (c) {
      if (phoneClient) phoneClient.stop();
      phoneClient = c;
      phoneClient.setNoDelay(true);
      bufPhone = "";
      Serial.printf("[PHONE] Connected from %s\n",
                    phoneClient.remoteIP().toString().c_str());
      sendToGCS("{\"info\":\"PHONE_CONNECTED\"}");
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ GCS
// ─────────────────────────────────────────────────────────────
void readGCS() {
  if (!gcsClient || !gcsClient.connected()) return;
  while (gcsClient.available()) {
    char ch = (char)gcsClient.read();
    if (ch == '\n') {
      bufGCS.trim();
      if (bufGCS.length() > 0) onGCSLine(decryptLine(bufGCS));
      bufGCS = "";
    } else {
      bufGCS += ch;
      if (bufGCS.length() > 768) bufGCS = "";
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ PHONE  (NMEA sentences from GPS Server app)
// ─────────────────────────────────────────────────────────────
void readPhone() {
  if (!phoneClient || !phoneClient.connected()) return;
  while (phoneClient.available()) {
    char ch = (char)phoneClient.read();
    if (ch == '\n') {
      bufPhone.trim();
      if (bufPhone.length() > 5) onPhoneLine(bufPhone);
      bufPhone = "";
    } else if (ch != '\r') {
      bufPhone += ch;
      if (bufPhone.length() > 128) bufPhone = "";
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ FC
// ─────────────────────────────────────────────────────────────
void readFC() {
  while (Serial2.available()) {
    char ch = (char)Serial2.read();
    if (ch == '\n') {
      bufFC.trim();
      if (bufFC.length() > 0) {
        if (bufFC.indexOf("\"roll\"") >= 0) {
          lastTelemJson = bufFC;
          wsServer.broadcastTXT(buildMergedTelem());
        }
        if (bufFC.indexOf("\"ack\"")  >= 0) lastAckJson = bufFC;
        sendToGCS(bufFC);
      }
      bufFC = "";
    } else {
      bufFC += ch;
      if (bufFC.length() > 512) bufFC = "";
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  GCS LINE HANDLER
// ─────────────────────────────────────────────────────────────
void onGCSLine(const String& line) {
  if (line.length() == 0) return;
  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) {
    Serial.printf("[GCS  ] Bad JSON: %.40s\n", line.c_str());
    return;
  }
  const char* cmd = doc["cmd"];
  if (!cmd) return;

  lastPing = millis();
  dmsFired = false;

  if (strcmp(cmd, "PING") == 0) return;  // DMS reset only, not forwarded

  Serial.printf("[GCS→FC] %s\n", cmd);
  sendToFC(line);
}

// ─────────────────────────────────────────────────────────────
//  PHONE LINE HANDLER  (NMEA sentences)
// ─────────────────────────────────────────────────────────────
void onPhoneLine(const String& line) {
  // NMEA sentence type is characters 3–5 (after the 2-char talker ID).
  // e.g. $GP GGA, $GN GGA, $GL GGA, $GA GGA, $GB GGA → all are "GGA"
  // This approach accepts all talker IDs (GP=GPS, GN=multi, GL=GLONASS,
  // GA=Galileo, GB=BeiDou) without listing every combination explicitly.
  if (line.length() < 6 || line[0] != '$') return;
  String stype = line.substring(3, 6);   // "GGA", "RMC", "GSA", etc.

  if (stype == "GGA") {
    parseGGA(line);
  } else if (stype == "RMC") {
    parseRMC(line);
  }
  // All other sentence types silently ignored.

  // When we have fresh data, mirror to GCS for display.
  // Reset gps.fresh immediately after forwarding so that if multiple
  // sentences arrive in the same readPhone() burst we don't send
  // the same position to the GCS twice.
  if (gps.fresh) {
    gps.fresh = false;
    StaticJsonDocument<256> fwd;
    fwd["type"]    = "phone";
    fwd["lat"]     = gps.lat;
    fwd["lon"]     = gps.lon;
    fwd["alt"]     = gps.alt;
    fwd["heading"] = gps.heading;
    fwd["baro_cm"] = gps.baro_cm;
    fwd["fix"]     = gps.fix;
    fwd["sats"]    = gps.sats;
    String fwdStr;
    serializeJson(fwd, fwdStr);
    sendToGCS(fwdStr);
    Serial.printf("[NMEA ] lat=%.6f  lon=%.6f  hdg=%.1f  fix=%d  sats=%d\n",
                  gps.lat, gps.lon, gps.heading, gps.fix, gps.sats);
  }
}

// ─────────────────────────────────────────────────────────────
//  DEAD-MAN SWITCH
// ─────────────────────────────────────────────────────────────
void checkDMS() {
  if (!dmsArmed || dmsFired) return;
  if (!gcsClient || !gcsClient.connected()) return;
  if (millis() - lastPing > DMS_TIMEOUT_MS) {
    dmsFired = true;
    Serial.println("[DMS  ] TIMEOUT — sending HOVER to FC");
    sendToFC("{\"cmd\":\"HOVER\"}");
    sendToGCS("{\"dms\":\"FIRED\",\"action\":\"HOVER\"}");
  }
}

// ─────────────────────────────────────────────────────────────
//  FORWARD GPS TO FC  (5 Hz)
// ─────────────────────────────────────────────────────────────
void forwardGPS() {
  if (!gps.fresh) return;
  if (millis() - lastGpsFwd < GPS_FWD_MS) return;
  lastGpsFwd = millis();
  gps.fresh  = false;

  StaticJsonDocument<256> doc;
  doc["cmd"]     = "GPS";
  doc["lat"]     = gps.lat;
  doc["lon"]     = gps.lon;
  doc["alt"]     = gps.alt;
  doc["heading"] = gps.heading;
  doc["baro_cm"] = gps.baro_cm;
  doc["fix"]     = gps.fix;
  doc["sats"]    = gps.sats;
  String out;
  serializeJson(doc, out);
  sendToFC(out);
}

// ─────────────────────────────────────────────────────────────
//  SEND HELPERS
// ─────────────────────────────────────────────────────────────
void sendToFC(const String& s) {
  Serial2.print(s);
  Serial2.print('\n');
}

void sendToGCS(const String& s) {
  if (!gcsClient || !gcsClient.connected()) return;
  String enc = encryptLine(s);
  gcsClient.print(enc);
  gcsClient.print('\n');
}

// ─────────────────────────────────────────────────────────────
//  STATUS LED
// ─────────────────────────────────────────────────────────────
void statusLED() {
  if (dmsFired) { digitalWrite(LED_PIN, HIGH); return; }
  static unsigned long lastLED = 0;
  static bool state = false;
  unsigned long iv = (gcsClient && gcsClient.connected()) ? 500 : 125;
  if (millis() - lastLED >= iv) {
    lastLED = millis();
    state   = !state;
    digitalWrite(LED_PIN, state);
  }
}
