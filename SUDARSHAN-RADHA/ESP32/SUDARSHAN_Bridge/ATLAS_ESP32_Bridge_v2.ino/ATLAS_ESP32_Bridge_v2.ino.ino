/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║       SUDARSHAN ESP32 BRIDGE FIRMWARE v2.0                  ║
 * ║       Project : RADHA / SUDARSHAN UAV                       ║
 * ║       Role    : WiFi AP ↔ UART bridge                       ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║                                                              ║
 * ║   ✦  Dedicated with deepest respect and gratitude to  ✦    ║
 * ║                                                              ║
 * ║           Ms. Neelrisham Singh                              ║
 * ║                                                              ║
 * ║      Whose kindness, guidance, and belief in this           ║
 * ║      project made every flight possible.                    ║
 * ║      May this work stand as a small tribute to you.         ║
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
//  GPS WEB PAGE  (served at http://192.168.4.1/)
//  Self-contained HTML+JS — no app required.
//  Phone opens this page, taps START, browser streams GPS via POST /gps.
//  Works on iOS Safari and Android Firefox/Samsung Browser out of the box.
//  Android Chrome needs a one-time flag:
//    chrome://flags/#unsafely-treat-insecure-origin-as-secure → add http://192.168.4.1
// ─────────────────────────────────────────────────────────────
static const char GPS_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0d0d0d">
<title>SUDARSHAN GPS</title>
<style>
body{background:#0d0d0d;color:#e0e0e0;font-family:monospace;padding:24px;text-align:center;margin:0}
h2{color:#00e5ff;margin:0 0 20px}
.val{font-size:1.3em;color:#00e676;margin:6px 0}
.err{color:#ff3b3b}.ok{color:#00e676}.dim{color:#555}
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
<script>
function go(){
  if(!navigator.geolocation){
    document.getElementById('st').innerHTML='<span class="err">Geolocation not supported by this browser</span>';return;
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
    var msg=e.message||'GPS error';
    var hint='';
    if(msg.indexOf('secure')!==-1||msg.indexOf('origin')!==-1||e.code===1){
      hint='<br><span class="dim">Using Chrome? One-time fix:<br>'
          +'1. Open chrome://flags/#unsafely-treat-insecure-origin-as-secure<br>'
          +'2. Add http://192.168.4.1 and set to Enabled<br>'
          +'3. Relaunch Chrome<br>'
          +'Or use Firefox / Safari instead.</span>';
    }
    document.getElementById('st').innerHTML='<span class="err">'+msg+'</span>'+hint;
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

unsigned long lastPing     = 0;
unsigned long lastGpsFwd   = 0;
bool          dmsArmed     = false;
bool          dmsFired     = false;
bool          phoneWasConn = false;

// ─────────────────────────────────────────────────────────────
//  HTTP GPS SERVER  (browser-based GPS — no app required)
// ─────────────────────────────────────────────────────────────
void handleRoot() {
  httpServer.send_P(200, "text/html", GPS_PAGE);
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
  httpServer.on("/",       HTTP_GET,  handleRoot);
  httpServer.on("/gps",    HTTP_POST, handleGpsPost);
  httpServer.on("/status", HTTP_GET,  handleStatus);
  httpServer.begin();
  Serial.println("[HTTP ] GPS web page at http://192.168.4.1/");
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
      if (bufFC.length() > 0) sendToGCS(bufFC);
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
