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
</div>

<div id="ovr">
  <div class="lbl">THROTTLE <span id="thrv">1050</span> us</div>
  <input id="thrsldr" type="range" min="1050" max="1900" value="1050"
    oninput="document.getElementById('thrv').textContent=this.value"
    onchange="sc('OVERRIDE',{throttle:parseInt(this.value)})">
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
  setDms(30);
  var b={cmd:cmd};
  if(extra){for(var k in extra)b[k]=extra[k];}
  fetch('/api/cmd',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(b)}).catch(function(){});
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

function pollTelem(){
  fetch('/api/telem').then(function(r){return r.json();}).then(function(d){
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
    if(d.last_ack){try{var a=JSON.parse(d.last_ack);var ab=document.getElementById('ackbar');ab.style.display='block';ab.textContent='FC: '+a.ack+' '+a.status+(a.msg?' — '+a.msg:'');clearTimeout(window._ackTm);window._ackTm=setTimeout(function(){ab.style.display='none';},6000);}catch(e){}}
    if(typeof d.roll==='number')drawAti(d.roll||0,d.pitch||0);
    if(d.gps_lat&&d.gps_lat!==0){
      document.getElementById('glat').textContent=d.gps_lat.toFixed(6);
      document.getElementById('glon').textContent=d.gps_lon.toFixed(6);
      document.getElementById('gfix').textContent=(d.gps_fix?'FIX':'---')+'/'+(d.gps_sats||0);
    }
  }).catch(function(){
    var lv=document.getElementById('live');
    lv.textContent='● OFFLINE';lv.style.color='#444';
  });
}
setInterval(pollTelem,1000);
pollTelem();

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
mtSel('FL');

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

// ─────────────────────────────────────────────────────────────
//  HTTP WEB GCS  (full GCS in phone browser — no laptop required)
// ─────────────────────────────────────────────────────────────
void handleRoot() {
  httpServer.send_P(200, "text/html", GCS_PAGE);
}

// GET /api/telem — returns last FC telemetry merged with GPS and ESP32 state
void handleWebTelem() {
  if (lastTelemJson.length() == 0) {
    httpServer.send(200, "application/json",
                    "{\"mode\":\"DISCONNECTED\",\"armed\":0}");
    return;
  }
  StaticJsonDocument<512> doc;
  deserializeJson(doc, lastTelemJson);
  doc["gps_lat"]  = gps.lat;
  doc["gps_lon"]  = gps.lon;
  doc["gps_fix"]  = gps.fix;
  doc["gps_sats"] = gps.sats;
  doc["gps_hdg"]  = gps.heading;
  doc["dms_ok"]   = !dmsFired;
  if (lastAckJson.length() > 0) {
    doc["last_ack"] = lastAckJson;
    lastAckJson = "";
  }
  String out;
  serializeJson(doc, out);
  httpServer.send(200, "application/json", out);
}

// POST /api/cmd — forwards command JSON to FC, resets ESP32 DMS
void handleWebCmd() {
  if (!httpServer.hasArg("plain")) { httpServer.send(400); return; }
  String body = httpServer.arg("plain");
  lastPing = millis();
  dmsFired = false;
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, body) == DeserializationError::Ok) {
    const char* cmd = doc["cmd"];
    if (cmd) {
      Serial.printf("[WEB→FC] %s\n", cmd);
      sendToFC(body);   // forward every command (incl. PING) to FC to keep FC DMS alive
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

void setupHTTP() {
  httpServer.on("/",          HTTP_GET,  handleRoot);
  httpServer.on("/api/telem", HTTP_GET,  handleWebTelem);
  httpServer.on("/api/cmd",   HTTP_POST, handleWebCmd);
  httpServer.on("/gps",       HTTP_POST, handleGpsPost);
  httpServer.on("/status",    HTTP_GET,  handleStatus);
  httpServer.begin();
  Serial.println("[HTTP ] Web GCS at http://192.168.4.1/");
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
  if (!gcsClient || !gcsClient.connected()) {
    WiFiClient c = gcsServer.available();
    if (c) {
      if (gcsClient) gcsClient.stop();
      gcsClient = c;
      gcsClient.setNoDelay(true);
      bufGCS   = "";
      lastPing = millis();
      dmsArmed = true;
      dmsFired = false;
      Serial.printf("[GCS  ] Connected from %s\n",
                    gcsClient.remoteIP().toString().c_str());
      sendToGCS("{\"info\":\"GCS_CONNECTED\"}");
    }
  }

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
        if (bufFC.indexOf("\"roll\"") >= 0) lastTelemJson = bufFC;
        if (bufFC.indexOf("\"ack\"")  >= 0) lastAckJson   = bufFC;
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
