/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║       SUDARSHAN ESP32 BRIDGE FIRMWARE v1.0                  ║
 * ║       Project : RADHA / SUDARSHAN UAV                       ║
 * ║       Role    : WiFi AP ↔ UART bridge                       ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  WIRING                                                      ║
 * ║    ESP32 GPIO17 (TX2) ──────────────► Mega2560 RX0 (Pin 0)  ║
 * ║    ESP32 GPIO16 (RX2) ◄──[DIVIDER]── Mega2560 TX0 (Pin 1)   ║
 * ║    Voltage divider on Mega TX:                               ║
 * ║      Mega TX ──[10kΩ]──┬──[20kΩ]── GND                     ║
 * ║                        └──► ESP32 GPIO16                    ║
 * ║    GND ────────────────────────────── GND (common)          ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  NETWORK                                                     ║
 * ║    SSID     : SUDARSHAN_AP                                   ║
 * ║    Password : radha2026                                      ║
 * ║    AP IP    : 192.168.4.1                                    ║
 * ║    GCS      → 192.168.4.1 : 5760  (TCP)                     ║
 * ║    Phone    → 192.168.4.1 : 5762  (TCP)                     ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  DEPENDENCIES                                                ║
 * ║    ArduinoJson v6  (Library Manager → search ArduinoJson)   ║
 * ╚══════════════════════════════════════════════════════════════╝
 *
 * ── RADHA PROTOCOL v1.0  (all newline-delimited JSON) ─────────
 *
 *  GCS → ESP32 → Mega2560  (ESP32 relays verbatim):
 *    {"cmd":"ARM"}
 *    {"cmd":"DISARM"}
 *    {"cmd":"HOVER"}
 *    {"cmd":"LAND"}
 *    {"cmd":"KILL"}
 *    {"cmd":"PING"}                ← resets DMS, NOT forwarded to FC
 *    {"cmd":"PRESET","segments":[
 *        {"bearing":0.0,"dist_m":5.0,"speed":0.5}, ...
 *    ]}
 *
 *  Phone → ESP32  (GPS/sensor data, ESP32 merges @ 5 Hz to FC):
 *    {"lat":28.6139,"lon":77.2090,"alt":215.0,
 *     "heading":182.3,"baro_cm":21500,"fix":1,"sats":8}
 *
 *  ESP32 → Mega2560  (GPS forwarded @ 5 Hz):
 *    {"cmd":"GPS","lat":28.6139,"lon":77.2090,"alt":215.0,
 *     "heading":182.3,"baro_cm":21500,"fix":1,"sats":8}
 *
 *  Mega2560 → ESP32 → GCS  (ESP32 relays verbatim):
 *    {"roll":0.0,"pitch":0.0,"yaw":0.0,"alt_cm":0,
 *     "bat_mv":12600,"mode":"HOVER","armed":1}
 *    {"ack":"ARM","status":"OK"}
 *    {"ack":"ARM","status":"ERR","msg":"reason"}
 *
 *  ESP32 → GCS only  (internal events):
 *    {"dms":"FIRED","action":"HOVER"}
 *    {"info":"GCS_CONNECTED"}
 *    {"info":"PHONE_CONNECTED"}
 *    {"info":"PHONE_DISCONNECTED"}
 */

#include <WiFi.h>
#include <ArduinoJson.h>

// ─────────────────────────────────────────────────────────────
//  CONFIG  (edit here only)
// ─────────────────────────────────────────────────────────────
#define WIFI_SSID      "SUDARSHAN_AP"
#define WIFI_PASS      "radha2026"

#define PORT_GCS       5760
#define PORT_PHONE     5762

#define FC_RX_PIN      16          // GPIO16 ← Mega TX  (via divider)
#define FC_TX_PIN      17          // GPIO17 → Mega RX
#define FC_BAUD        115200

#define DMS_TIMEOUT_MS 30000UL     // 30s no PING → HOVER
#define GPS_FWD_MS     200UL       // 5 Hz GPS forward rate to FC
#define LED_PIN        2           // built-in LED on most ESP32 devkits

static const IPAddress AP_IP (192, 168, 4, 1);
static const IPAddress AP_GW (192, 168, 4, 1);
static const IPAddress AP_SN (255, 255, 255, 0);

// ─────────────────────────────────────────────────────────────
//  GLOBALS
// ─────────────────────────────────────────────────────────────
WiFiServer gcsServer(PORT_GCS);
WiFiServer phoneServer(PORT_PHONE);
WiFiClient gcsClient;
WiFiClient phoneClient;

// Receive buffers (newline-delimited, one per source)
String bufFC    = "";
String bufGCS   = "";
String bufPhone = "";

// Latest GPS state from phone
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

unsigned long lastPing   = 0;
unsigned long lastGpsFwd = 0;
bool          dmsArmed   = false;   // true once GCS connects
bool          dmsFired   = false;

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // ── UART to Mega2560 ───────────────────────────────────────
  Serial2.begin(FC_BAUD, SERIAL_8N1, FC_RX_PIN, FC_TX_PIN);
  Serial.println("[UART ] Serial2 up @ 115200  RX=" +
                 String(FC_RX_PIN) + "  TX=" + String(FC_TX_PIN));

  // ── WiFi AP ────────────────────────────────────────────────
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GW, AP_SN);
  bool ok = WiFi.softAP(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi ] AP %s  SSID: %s  IP: %s\n",
                ok ? "OK" : "FAIL",
                WIFI_SSID,
                WiFi.softAPIP().toString().c_str());

  // ── TCP servers ────────────────────────────────────────────
  gcsServer.begin();
  phoneServer.begin();
  Serial.printf("[TCP  ] GCS   :%d   Phone :%d\n", PORT_GCS, PORT_PHONE);

  // 3 quick blinks = ready
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
  // GCS client — only one at a time
  if (!gcsClient || !gcsClient.connected()) {
    WiFiClient c = gcsServer.available();
    if (c) {
      if (gcsClient) gcsClient.stop();
      gcsClient = c;
      gcsClient.setNoDelay(true);
      bufGCS    = "";
      lastPing  = millis();
      dmsArmed  = true;
      dmsFired  = false;
      Serial.printf("[GCS  ] Connected from %s\n",
                    gcsClient.remoteIP().toString().c_str());
      sendToGCS("{\"info\":\"GCS_CONNECTED\"}");
    }
  }

  // Phone client — only one at a time
  if (!phoneClient || !phoneClient.connected()) {
    WiFiClient c = phoneServer.available();
    if (c) {
      if (phoneClient) phoneClient.stop();
      phoneClient = c;
      phoneClient.setNoDelay(true);
      bufPhone    = "";
      Serial.printf("[PHONE] Connected from %s\n",
                    phoneClient.remoteIP().toString().c_str());
      sendToGCS("{\"info\":\"PHONE_CONNECTED\"}");
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ GCS (TCP → buffer → parse lines)
// ─────────────────────────────────────────────────────────────
void readGCS() {
  if (!gcsClient || !gcsClient.connected()) return;

  while (gcsClient.available()) {
    char ch = (char)gcsClient.read();
    if (ch == '\n') {
      bufGCS.trim();
      if (bufGCS.length() > 0) onGCSLine(bufGCS);
      bufGCS = "";
    } else {
      bufGCS += ch;
      if (bufGCS.length() > 512) bufGCS = ""; // overflow guard
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ PHONE (TCP → buffer → parse lines)
// ─────────────────────────────────────────────────────────────
void readPhone() {
  if (!phoneClient || !phoneClient.connected()) return;

  while (phoneClient.available()) {
    char ch = (char)phoneClient.read();
    if (ch == '\n') {
      bufPhone.trim();
      if (bufPhone.length() > 0) onPhoneLine(bufPhone);
      bufPhone = "";
    } else {
      bufPhone += ch;
      if (bufPhone.length() > 512) bufPhone = "";
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  READ FC  (UART → buffer → forward to GCS)
// ─────────────────────────────────────────────────────────────
void readFC() {
  while (Serial2.available()) {
    char ch = (char)Serial2.read();
    if (ch == '\n') {
      bufFC.trim();
      if (bufFC.length() > 0) {
        sendToGCS(bufFC);               // telemetry + ACKs go straight to GCS
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
  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) {
    Serial.printf("[GCS  ] Bad JSON: %s\n", line.c_str());
    return;
  }

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  // Always reset DMS on any valid packet from GCS
  lastPing = millis();
  dmsFired = false;

  if (strcmp(cmd, "PING") == 0) {
    // PING only resets DMS — not forwarded to FC
    return;
  }

  // All other commands relay verbatim to FC
  Serial.printf("[GCS→FC] %s\n", cmd);
  sendToFC(line);
}

// ─────────────────────────────────────────────────────────────
//  PHONE LINE HANDLER
// ─────────────────────────────────────────────────────────────
void onPhoneLine(const String& line) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) return;

  if (doc.containsKey("lat"))     gps.lat     = doc["lat"].as<double>();
  if (doc.containsKey("lon"))     gps.lon     = doc["lon"].as<double>();
  if (doc.containsKey("alt"))     gps.alt     = doc["alt"].as<float>();
  if (doc.containsKey("heading")) gps.heading = doc["heading"].as<float>();
  if (doc.containsKey("baro_cm")) gps.baro_cm = doc["baro_cm"].as<int>();
  if (doc.containsKey("fix"))     gps.fix     = doc["fix"].as<int>();
  if (doc.containsKey("sats"))    gps.sats    = doc["sats"].as<int>();
  gps.fresh = true;

  // Mirror phone data to GCS for live display
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

  Serial.printf("[PHONE→GCS] lat=%.6f  lon=%.6f  hdg=%.1f°  fix=%d  sats=%d\n",
                gps.lat, gps.lon, gps.heading, gps.fix, gps.sats);
}

// ─────────────────────────────────────────────────────────────
//  DEAD-MAN SWITCH
// ─────────────────────────────────────────────────────────────
void checkDMS() {
  if (!dmsArmed)  return;
  if (dmsFired)   return;
  if (!gcsClient || !gcsClient.connected()) return;

  if (millis() - lastPing > DMS_TIMEOUT_MS) {
    dmsFired = true;
    Serial.println("[DMS  ] TIMEOUT — sending HOVER to FC");
    sendToFC("{\"cmd\":\"HOVER\"}");
    sendToGCS("{\"dms\":\"FIRED\",\"action\":\"HOVER\"}");
  }
}

// ─────────────────────────────────────────────────────────────
//  FORWARD GPS TO FC  (rate-limited to GPS_FWD_MS)
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
  if (gcsClient && gcsClient.connected()) {
    gcsClient.print(s);
    gcsClient.print('\n');
  }
}

// ─────────────────────────────────────────────────────────────
//  STATUS LED
//  No GCS      → fast blink  125ms
//  GCS ready   → slow pulse  500ms
//  DMS fired   → solid ON
// ─────────────────────────────────────────────────────────────
void statusLED() {
  if (dmsFired) {
    digitalWrite(LED_PIN, HIGH);
    return;
  }

  static unsigned long lastLED = 0;
  static bool          state   = false;
  unsigned long        iv = (gcsClient && gcsClient.connected()) ? 500 : 125;

  if (millis() - lastLED >= iv) {
    lastLED = millis();
    state   = !state;
    digitalWrite(LED_PIN, state);
  }
}
