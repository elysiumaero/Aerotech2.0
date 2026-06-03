/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║       SUDARSHAN FC — Arduino Mega2560 v1.0                  ║
 * ║       Project : RADHA / SUDARSHAN UAV                       ║
 * ║       Loop    : 250Hz control  |  10Hz telemetry            ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  WIRING                                                      ║
 * ║    MPU6050  SDA → Pin 20  |  SCL → Pin 21   (I2C)           ║
 * ║    HC-SR04  Trig → D7     |  Echo → D8                      ║
 * ║    Uno Motor Driver  ← Serial2 (TX=Pin16  RX=Pin17)         ║
 * ║    ESC signals via PCA9685 on Uno (CH0=FL 1=FR 2=RL 3=RR)  ║
 * ║    Battery  → A0  (via divider: 47kΩ + 10kΩ for 3S)        ║
 * ║    ESP32 TX → Pin 19 (Serial1 RX)                           ║
 * ║    ESP32 RX → Pin 18 (Serial1 TX)  [3.3V safe, no divider] ║
 * ║    ⚠ Update ESP32 firmware wiring to pins 18/19 on Mega     ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  LIBRARIES                                                   ║
 * ║    Wire.h · ArduinoJson v6  (Adafruit driver lives on Uno)  ║
 * ╚══════════════════════════════════════════════════════════════╝
 */

#include <Wire.h>
#include <ArduinoJson.h>

// ─────────────────────────────────────────────────────────────
//  CONFIG
// ─────────────────────────────────────────────────────────────

// Serials
#define ESP_SERIAL   Serial1   // pins 18(TX) / 19(RX) — to ESP32
#define DBG_SERIAL   Serial    // USB debug

// Uno motor driver — Serial2 (Mega TX2=Pin16, RX2=Pin17)
#define UNO_SERIAL  Serial2
#define UNO_BAUD    115200

// Sonar pins
#define PIN_TRIG  7
#define PIN_ECHO  8

// Battery
#define PIN_BATT    A0
// 3S LiPo: divider 47kΩ + 10kΩ  → scale = 5000/1023 * (57/10)
#define BATT_SCALE  (5000.0f / 1023.0f * 5.7f)

// ESC limits (µs) — TUNE ESC_IDLE for your all-up weight
#define ESC_ARM   1000
#define ESC_MIN   1050
#define ESC_IDLE  1150    // ← tune this: throttle at which drone just lifts
#define ESC_MAX   1950

// Battery thresholds (mV) — 3S LiPo
#define BAT_WARN_MV  10500   // alert: land soon
#define BAT_CRIT_MV   9900   // auto-LAND triggered immediately

// Loop timing
#define LOOP_HZ       250
#define LOOP_US       (1000000UL / LOOP_HZ)   // 4000µs
#define TELEM_EVERY   25                       // every 25 loops = 10Hz

// DMS: if no command for 30s → FAILSAFE
#define DMS_TIMEOUT_MS  30000UL

// Complementary filter weight (0.98 = trust gyro heavily)
#define CF_ALPHA  0.98f

// IMU yaw sign — flip to -1 if yaw drifts the WRONG direction on bench.
// With MPU6050 Z-axis pointing UP  → keep at  1.
// With MPU6050 Z-axis pointing DOWN → change to -1.
#define IMU_YAW_SIGN  1

// PID output limits (µs added to throttle)
#define LIM_RP   300.0f
#define LIM_YAW  120.0f
#define LIM_ALT  250.0f

// Preset mission
#define MAX_SEGS   16
#define FLY_SPEED  2.0f    // m/s assumed at speed=1.0

// ─────────────────────────────────────────────────────────────
//  FLIGHT MODES
// ─────────────────────────────────────────────────────────────
typedef enum {
  MODE_DISARMED  = 0,
  MODE_HOVER     = 1,
  MODE_LAND      = 2,
  MODE_RTL       = 3,
  MODE_OVERRIDE  = 4,
  MODE_FAILSAFE  = 5,
  MODE_KILL      = 6,
  MODE_IMUMISSION = 7,
} FlightMode;

const char* MODE_NAME[] = {
  "DISARMED","HOVER","LAND","RTL",
  "OVERRIDE","FAILSAFE","KILL","IMUMISSION"
};

// ─────────────────────────────────────────────────────────────
//  PID
// ─────────────────────────────────────────────────────────────
struct PID {
  float kp, ki, kd, lim;
  float integ, prev_e;

  void init(float p, float i, float d, float l) {
    kp=p; ki=i; kd=d; lim=l;
    integ=0; prev_e=0;
  }

  float compute(float sp, float meas, float dt) {
    float e  = sp - meas;
    integ   += e * dt;
    float il  = (ki > 0.001f) ? lim / ki : lim;
    integ     = constrain(integ, -il, il);
    float out = kp*e + ki*integ + kd*((e - prev_e) / dt);
    prev_e    = e;
    return constrain(out, -lim, lim);
  }

  void reset() { integ=0; prev_e=0; }
};

// ─────────────────────────────────────────────────────────────
//  MISSION SEGMENT
// ─────────────────────────────────────────────────────────────
struct Segment { float bearing, dist_m, speed; };
typedef enum { SEG_TURN=0, SEG_FLY, SEG_PAUSE } SegPhase;

// ─────────────────────────────────────────────────────────────
//  GLOBALS
// ─────────────────────────────────────────────────────────────

// (ESC output handled by Uno motor driver — see SUDARSHAN_MOTOR_UNO)

// Motor-channel mapping set by the GCS motor-ID wizard.
// motorMap[pos] = PCA9685 channel.  pos: 0=FL 1=FR 2=RL 3=RR
// Default is identity (channel N = motor N) until wizard runs.
uint8_t motorMap[4] = {0, 1, 2, 3};

// PIDs
PID pidRoll, pidPitch, pidYaw, pidAlt;

// Flight state
FlightMode mode = MODE_DISARMED;

// IMU
float accX, accY, accZ;           // g
float gyrX, gyrY, gyrZ;           // deg/s (calibration applied)
float gyrCal[3]    = {0,0,0};
float roll_cf      = 0;
float pitch_cf     = 0;
float yaw_gyro     = 0;

// Altitude
float alt_cm          = 0;
float target_alt      = 0;
uint8_t landCount     = 0;           // debounce for landing detect
unsigned long sonarValidMs = 0;      // last millis() sonar returned >0
bool  sonarStale      = false;       // true when sonar has been 0 for >500ms

// Battery (cached so we don't spam analogRead at 250Hz)
int   bat_mv_cached   = 12600;

// Setpoints
float sp_roll      = 0;
float sp_pitch     = 0;
float sp_yaw       = 0;
int   base_thr     = ESC_IDLE;

// GPS (received from phone via ESP32)
double gps_lat = 0, gps_lon = 0;
float  gps_alt = 0, gps_hdg = 0;
int    gps_baro_cm = 0, gps_fix = 0, gps_sats = 0;
double home_lat = 0, home_lon = 0;

// Mission
Segment segs[MAX_SEGS];
int       segCount = 0, curSeg = 0;
SegPhase  segPhase = SEG_TURN;
unsigned long segTimer = 0;

// Timing
unsigned long lastLoopUs  = 0;
unsigned long lastCmdMs   = 0;
unsigned long landTimer   = 0;
unsigned long loopCount   = 0;

// UART receive buffer — fixed size prevents heap fragmentation
static char uartBuf[256];
static uint8_t uartLen = 0;

// ─────────────────────────────────────────────────────────────
//  MPU6050  (direct I2C register access)
// ─────────────────────────────────────────────────────────────

// Address is probed at init — AD0 LOW → 0x68, AD0 HIGH → 0x69
static uint8_t MPU = 0x68;
bool imuOk = false;

void mpuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU);
  Wire.write(reg); Wire.write(val);
  Wire.endTransmission();
}

bool mpuInit() {
  Wire.begin();
  Wire.setClock(400000);
  delay(50);

  // Probe both I2C addresses — AD0 pin determines which one is active
  const uint8_t addrs[2] = {0x68, 0x69};
  for (uint8_t i = 0; i < 2; i++) {
    Wire.beginTransmission(addrs[i]);
    if (Wire.endTransmission() == 0) { MPU = addrs[i]; break; }
  }

  mpuWrite(0x6B, 0x00);  // wake
  mpuWrite(0x1B, 0x00);  // gyro  ±250 °/s
  mpuWrite(0x1C, 0x00);  // accel ±2 g
  mpuWrite(0x1A, 0x03);  // DLPF 43 Hz
  Wire.beginTransmission(MPU);
  Wire.write(0x75);
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)MPU, (uint8_t)1);
  if (!Wire.available()) return false;
  uint8_t who = Wire.read();
  return (who == 0x68 || who == 0x69);  // WHO_AM_I register value
}

void mpuRead() {
  Wire.beginTransmission(MPU);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)MPU, (uint8_t)14);
  if (Wire.available() < 14) return;

  int16_t ax = (Wire.read()<<8)|Wire.read();
  int16_t ay = (Wire.read()<<8)|Wire.read();
  int16_t az = (Wire.read()<<8)|Wire.read();
  Wire.read(); Wire.read();                     // temperature skip
  int16_t gx = (Wire.read()<<8)|Wire.read();
  int16_t gy = (Wire.read()<<8)|Wire.read();
  int16_t gz = (Wire.read()<<8)|Wire.read();

  accX = ax / 16384.0f;
  accY = ay / 16384.0f;
  accZ = az / 16384.0f;
  gyrX = gx / 131.0f - gyrCal[0];
  gyrY = gy / 131.0f - gyrCal[1];
  gyrZ = gz / 131.0f - gyrCal[2];
}

void mpuCalibrate() {
  DBG_SERIAL.println("[IMU ] Calibrating — keep still...");
  float sx=0, sy=0, sz=0;
  for (int i = 0; i < 500; i++) {
    mpuRead();
    sx += gyrX; sy += gyrY; sz += gyrZ;
    delay(4);
  }
  gyrCal[0] = sx/500.0f;
  gyrCal[1] = sy/500.0f;
  gyrCal[2] = sz/500.0f;
  char _imbuf[64];
  snprintf(_imbuf, sizeof(_imbuf), "[IMU ] Offsets: %.3f / %.3f / %.3f",
           gyrCal[0], gyrCal[1], gyrCal[2]);
  DBG_SERIAL.println(_imbuf);
}

void computeAngles(float dt) {
  float aRoll  =  atan2f(accY, accZ)                        * 57.2958f;
  float aPitch = atan2f(-accX, sqrtf(accY*accY + accZ*accZ)) * 57.2958f;
  float gxClamped = constrain(gyrX, -250.0f, 250.0f);
  float gyClamped = constrain(gyrY, -250.0f, 250.0f);
  roll_cf   = CF_ALPHA*(roll_cf  + gxClamped*dt) + (1-CF_ALPHA)*aRoll;
  pitch_cf  = CF_ALPHA*(pitch_cf + gyClamped*dt) + (1-CF_ALPHA)*aPitch;
  float gzClamped = constrain(gyrZ, -250.0f, 250.0f);
  yaw_gyro += (IMU_YAW_SIGN * gzClamped) * dt;
  if (yaw_gyro >  180) yaw_gyro -= 360;
  if (yaw_gyro < -180) yaw_gyro += 360;
}

// ─────────────────────────────────────────────────────────────
//  SONAR  (non-blocking read via pulseIn with timeout)
// ─────────────────────────────────────────────────────────────
float readSonar() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  // 23ms timeout → 4m max range.
  // NOTE: called from the main loop at 25 Hz, NOT inside the 250Hz control
  // loop, so this blocking call does NOT corrupt the dt calculation.
  long d = pulseIn(PIN_ECHO, HIGH, 23000);
  if (d > 150) {               // reject pulses < 150µs (< 2.6 cm — noise/crosstalk)
    float raw    = d * 0.01715f;
    sonarValidMs = millis();
    sonarStale   = false;
    if (alt_cm < 1.0f) return raw;   // cold-start: use raw directly, skip EMA
    // EMA: blend 40% new reading into 60% running value — rejects single spikes
    // while tracking real altitude changes within a few readings.
    return alt_cm * 0.60f + raw * 0.40f;
  }
  if (millis() - sonarValidMs > 500) sonarStale = true;
  return alt_cm;               // hold last valid value
}

// ─────────────────────────────────────────────────────────────
//  ESCs  (via Uno motor driver — 10-byte binary packet over Serial2)
//  Packet: [0xAA][fl_H][fl_L][fr_H][fr_L][rl_H][rl_L][rr_H][rr_L][xor]
// ─────────────────────────────────────────────────────────────
void sendMotors(uint16_t fl, uint16_t fr, uint16_t rl, uint16_t rr) {
  uint8_t pkt[10];
  pkt[0] = 0xAA;
  pkt[1] = fl >> 8;  pkt[2] = fl & 0xFF;
  pkt[3] = fr >> 8;  pkt[4] = fr & 0xFF;
  pkt[5] = rl >> 8;  pkt[6] = rl & 0xFF;
  pkt[7] = rr >> 8;  pkt[8] = rr & 0xFF;
  uint8_t xorChk = 0;
  for (uint8_t i = 1; i < 9; i++) xorChk ^= pkt[i];
  pkt[9] = xorChk;
  UNO_SERIAL.write(pkt, 10);
}

// Route FL/FR/RL/RR values to the correct PCA9685 channels
// using the mapping saved by the GCS motor-ID wizard.
void sendMotorsPos(uint16_t fl, uint16_t fr, uint16_t rl, uint16_t rr) {
  uint16_t v[4] = {ESC_ARM, ESC_ARM, ESC_ARM, ESC_ARM};
  v[motorMap[0]] = fl;
  v[motorMap[1]] = fr;
  v[motorMap[2]] = rl;
  v[motorMap[3]] = rr;
  sendMotors(v[0], v[1], v[2], v[3]);
}

void escsWrite(int fl, int fr, int rl, int rr) {
  sendMotorsPos(
    (uint16_t)constrain(fl, ESC_MIN, ESC_MAX),
    (uint16_t)constrain(fr, ESC_MIN, ESC_MAX),
    (uint16_t)constrain(rl, ESC_MIN, ESC_MAX),
    (uint16_t)constrain(rr, ESC_MIN, ESC_MAX)
  );
}

void escsKill() {
  sendMotors(ESC_ARM, ESC_ARM, ESC_ARM, ESC_ARM);
}

void escsArm() {
  escsKill();
  delay(2500);  // hold min throttle for ESC arming beeps
}

// ─────────────────────────────────────────────────────────────
//  MOTOR MIXING  — X-frame (top-view)
//
//     FL(↺)  FR(↻)      +roll  → right bank  → FL+  FR-  RL+  RR-
//       ╲   ╱           +pitch → nose up      → FL+  FR+  RL-  RR-
//       ╱   ╲           +yaw   → CW spin      → FL-  FR+  RL+  RR-
//     RL(↻)  RR(↺)
//
//  ⚠ If drone yaws/rolls wrong direction on bench, flip sign of
//    that axis in the mix below. Do NOT change PID gains first.
// ─────────────────────────────────────────────────────────────
void motorMix(int thr, float r, float p, float y) {
  int fl = thr + (int)( p + r - y);
  int fr = thr + (int)( p - r + y);
  int rl = thr + (int)(-p + r + y);
  int rr = thr + (int)(-p - r - y);
  // Proportional scale-down: if any motor exceeds ESC_MAX, scale ALL motors
  // by the same factor so attitude ratios are preserved.
  int hi = max(max(fl, fr), max(rl, rr));
  if (hi > ESC_MAX) {
    float scale = (float)(ESC_MAX - ESC_MIN) / (float)(hi - ESC_MIN);
    fl = ESC_MIN + (int)((fl - ESC_MIN) * scale);
    fr = ESC_MIN + (int)((fr - ESC_MIN) * scale);
    rl = ESC_MIN + (int)((rl - ESC_MIN) * scale);
    rr = ESC_MIN + (int)((rr - ESC_MIN) * scale);
  }
  escsWrite(fl, fr, rl, rr);
}

// ─────────────────────────────────────────────────────────────
//  ACK helper
// ─────────────────────────────────────────────────────────────
void ack(const char* cmd, bool ok, const char* msg = "") {
  StaticJsonDocument<128> d;
  d["ack"]    = cmd;
  d["status"] = ok ? "OK" : "ERR";
  if (msg[0]) d["msg"] = msg;
  String s; serializeJson(d, s);
  ESP_SERIAL.println(s);
}

// ─────────────────────────────────────────────────────────────
//  COMMAND HANDLER
// ─────────────────────────────────────────────────────────────
void handleCmd(const String& line) {
  StaticJsonDocument<768> doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) return;

  const char* cmd = doc["cmd"] | "";
  if (!cmd[0]) return;

  lastCmdMs = millis();   // reset DMS on every valid packet

  // ── PING ──────────────────────────────────────────────────
  if (!strcmp(cmd, "PING")) return;

  // ── ARM ───────────────────────────────────────────────────
  if (!strcmp(cmd, "ARM")) {
    if (!imuOk) { ack("ARM", false, "IMU not found — check SDA/SCL/VCC wiring"); return; }
    if (mode != MODE_DISARMED) { ack("ARM",false,"already armed"); return; }
    home_lat = gps_lat;  home_lon = gps_lon;
    pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
    sp_roll=0; sp_pitch=0; sp_yaw=yaw_gyro;
    base_thr    = ESC_IDLE;
    target_alt  = alt_cm;
    if (target_alt < 10.0f) target_alt = 30.0f;   // sonar cold/failed — safe default
    escsArm();
    mode = MODE_HOVER;
    ack("ARM", true);
    return;
  }

  // ── FORCE_ARM  (admin password override — bypasses all pre-flight checks) ──
  if (!strcmp(cmd, "FORCE_ARM")) {
    if (mode != MODE_DISARMED) { ack("FORCE_ARM", false, "already armed"); return; }
    home_lat = gps_lat;  home_lon = gps_lon;
    pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
    sp_roll=0; sp_pitch=0; sp_yaw=yaw_gyro;
    base_thr   = ESC_IDLE;
    target_alt = alt_cm;
    escsArm();
    mode = MODE_HOVER;
    ack("FORCE_ARM", true, "IMU checks bypassed by admin");
    return;
  }

  // ── DISARM ────────────────────────────────────────────────
  if (!strcmp(cmd, "DISARM")) {
    mode = MODE_DISARMED;
    escsKill();
    ack("DISARM", true);
    return;
  }

  // ── HOVER ─────────────────────────────────────────────────
  if (!strcmp(cmd, "HOVER")) {
    if (mode == MODE_DISARMED || mode == MODE_KILL) {
      ack("HOVER", false, "not armed"); return;
    }
    pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
    mode      = MODE_HOVER;
    sp_roll=0; sp_pitch=0; sp_yaw=yaw_gyro;
    target_alt = alt_cm;
    ack("HOVER", true);
    return;
  }

  // ── ALT_HOLD  {"cmd":"ALT_HOLD","alt_cm":150}
  if (!strcmp(cmd, "ALT_HOLD")) {
    if (mode == MODE_DISARMED || mode == MODE_KILL) {
      ack("ALT_HOLD", false, "not armed"); return;
    }
    float a = doc["alt_cm"] | target_alt;
    target_alt = constrain(a, 30.0f, 500.0f);
    char mbuf[32];
    snprintf(mbuf, sizeof(mbuf), "target=%dcm", (int)target_alt);
    ack("ALT_HOLD", true, mbuf);
    return;
  }

  // ── LAND ──────────────────────────────────────────────────
  if (!strcmp(cmd, "LAND")) {
    if (mode == MODE_DISARMED || mode == MODE_KILL) {
      ack("LAND", false, "not armed"); return;
    }
    pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
    sp_roll=0; sp_pitch=0;
    landTimer = millis(); landCount = 0;
    mode = MODE_LAND;
    ack("LAND", true);
    return;
  }

  // ── KILL ──────────────────────────────────────────────────
  if (!strcmp(cmd, "KILL")) {
    mode = MODE_KILL;
    escsKill();
    ack("KILL", true);
    return;
  }

  // ── OVERRIDE  {"cmd":"OVERRIDE","roll":5,"pitch":-3,"yaw":0,"throttle":1180}
  if (!strcmp(cmd, "OVERRIDE")) {
    if (mode == MODE_DISARMED || mode == MODE_KILL) {
      ack("OVERRIDE", false, "not armed"); return;
    }
    mode      = MODE_OVERRIDE;
    sp_roll   = doc["roll"]     | 0.0f;
    sp_pitch  = doc["pitch"]    | 0.0f;
    sp_yaw    = doc["yaw"]      | sp_yaw;
    base_thr  = doc["throttle"] | ESC_IDLE;
    return;
  }

  // ── GPS ───────────────────────────────────────────────────
  if (!strcmp(cmd, "GPS")) {
    gps_lat    = doc["lat"]     | (double)0.0;
    gps_lon    = doc["lon"]     | (double)0.0;
    gps_alt    = doc["alt"]     | 0.0f;
    gps_hdg    = doc["heading"] | 0.0f;
    gps_baro_cm= doc["baro_cm"] | 0;
    gps_fix    = doc["fix"]     | 0;
    gps_sats   = doc["sats"]    | 0;
    // Slow compass correction — only when GPS is fresh and drone is stable
    if (gps_fix && !sonarStale) {
      float diff = gps_hdg - yaw_gyro;
      while (diff >  180) diff -= 360;
      while (diff < -180) diff += 360;
      float corr = 0.005f * diff;
      // Cap single-step correction to ±0.5° to prevent stale GPS yanking heading
      if (corr >  0.5f) corr =  0.5f;
      if (corr < -0.5f) corr = -0.5f;
      yaw_gyro += corr;
    }
    return;
  }

  // ── MOTOR_TEST  {"cmd":"MOTOR_TEST","motor":"FL","throttle":1100,"duration_ms":1500}
  // Only accepted in DISARMED state — for bench testing with props OFF.
  if (!strcmp(cmd, "MOTOR_TEST")) {
    if (mode != MODE_DISARMED) { ack("MOTOR_TEST", false, "must be DISARMED"); return; }
    const char* motor = doc["motor"] | "FL";
    int  thr = constrain(doc["throttle"]    | 1100, ESC_MIN, 1200);  // hard cap 1200µs
    unsigned long dur = constrain((unsigned long)(doc["duration_ms"] | 1000),
                                  200UL, 2000UL);
    uint16_t fl = ESC_ARM, fr = ESC_ARM, rl = ESC_ARM, rr = ESC_ARM;
    if      (!strcmp(motor, "FL")) fl = (uint16_t)thr;
    else if (!strcmp(motor, "FR")) fr = (uint16_t)thr;
    else if (!strcmp(motor, "RL")) rl = (uint16_t)thr;
    else if (!strcmp(motor, "RR")) rr = (uint16_t)thr;
    else { ack("MOTOR_TEST", false, "bad motor"); return; }
    escsKill();
    delay(500);
    sendMotors(fl, fr, rl, rr);   // only selected motor gets thr; others stay at ESC_ARM
    delay(dur);        // blocking OK — drone is DISARMED on bench
    escsKill();
    ack("MOTOR_TEST", true, motor);
    return;
  }

  // ── SPIN_CH  {"cmd":"SPIN_CH","ch":0,"thr":1100,"dur":2000}  ─
  // Spin a raw PCA9685 channel by index — used by motor-ID wizard.
  // Bypasses motorMap intentionally (wizard builds the map).
  if (!strcmp(cmd, "SPIN_CH")) {
    if (mode != MODE_DISARMED) { ack("SPIN_CH", false, "must be DISARMED"); return; }
    int ch  = constrain(doc["ch"]  | 0, 0, 3);
    int thr = constrain(doc["thr"] | 1100, ESC_MIN, 1200);
    unsigned long dur = constrain((unsigned long)(doc["dur"] | 2000), 500UL, 3000UL);
    uint16_t v[4] = {ESC_ARM, ESC_ARM, ESC_ARM, ESC_ARM};
    v[ch] = (uint16_t)thr;
    escsKill(); delay(300);
    sendMotors(v[0], v[1], v[2], v[3]);
    delay(dur);
    escsKill();
    ack("SPIN_CH", true);
    return;
  }

  // ── SET_MOTOR_MAP  {"cmd":"SET_MOTOR_MAP","fl":2,"fr":0,"rl":3,"rr":1}
  // Save channel-to-motor mapping from the GCS motor-ID wizard.
  if (!strcmp(cmd, "SET_MOTOR_MAP")) {
    if (mode != MODE_DISARMED) { ack("SET_MOTOR_MAP", false, "must be DISARMED"); return; }
    motorMap[0] = constrain(doc["fl"] | 0, 0, 3);
    motorMap[1] = constrain(doc["fr"] | 1, 0, 3);
    motorMap[2] = constrain(doc["rl"] | 2, 0, 3);
    motorMap[3] = constrain(doc["rr"] | 3, 0, 3);
    char mbuf[48];
    snprintf(mbuf, sizeof(mbuf), "FL=CH%d FR=CH%d RL=CH%d RR=CH%d",
             motorMap[0], motorMap[1], motorMap[2], motorMap[3]);
    ack("SET_MOTOR_MAP", true, mbuf);
    return;
  }

  // ── CAL_ESC  (one-time ESC throttle-range calibration) ───────
  // Standard procedure: full throttle → ESC double-beep → minimum
  // throttle → ESC confirms. Run once per ESC, props OFF.
  if (!strcmp(cmd, "CAL_ESC")) {
    if (mode != MODE_DISARMED) { ack("CAL_ESC", false, "must be DISARMED"); return; }
    DBG_SERIAL.println(F("[ESC ] CAL — sending 2000us (listen for double-beep)..."));
    sendMotors(2000, 2000, 2000, 2000);
    delay(3000);
    DBG_SERIAL.println(F("[ESC ] CAL — sending 1000us (listen for confirm beeps)..."));
    sendMotors(ESC_ARM, ESC_ARM, ESC_ARM, ESC_ARM);
    delay(3000);
    DBG_SERIAL.println(F("[ESC ] CAL done"));
    ack("CAL_ESC", true, "ESCs calibrated — cycle power to confirm");
    return;
  }

  // ── PRESET ────────────────────────────────────────────────
  if (!strcmp(cmd, "PRESET")) {
    if (mode == MODE_DISARMED || mode == MODE_KILL) {
      ack("PRESET", false, "not armed"); return;
    }
    JsonArray arr = doc["segments"].as<JsonArray>();
    segCount = 0;
    for (JsonObject s : arr) {
      if (segCount >= MAX_SEGS) break;
      float segDist = s["dist_m"] | 1.0f;
      if (segDist < 0.1f) segDist = 0.1f;   // prevent division-by-zero in flyMs calc
      segs[segCount++] = {
        s["bearing"] | 0.0f,
        segDist,
        constrain(s["speed"] | 0.5f, 0.1f, 1.0f)
      };
    }
    if (!segCount) { ack("PRESET", false, "no segments"); return; }
    curSeg   = 0;
    segPhase = SEG_TURN;
    segTimer = millis();
    mode     = MODE_IMUMISSION;
    ack("PRESET", true);
    return;
  }
}

// ─────────────────────────────────────────────────────────────
//  MISSION UPDATE  (called each 250Hz loop in IMUMISSION mode)
// ─────────────────────────────────────────────────────────────
void updateMission() {
  if (curSeg >= segCount) {
    mode = MODE_HOVER;
    sp_roll=0; sp_pitch=0; sp_yaw=yaw_gyro;
    return;
  }

  Segment& s       = segs[curSeg];
  unsigned long el = millis() - segTimer;

  switch (segPhase) {

    case SEG_TURN: {
      // Target absolute yaw = bearing
      sp_roll=0; sp_pitch=0;
      sp_yaw = s.bearing;
      float err = sp_yaw - yaw_gyro;
      while (err >  180) err -= 360;
      while (err < -180) err += 360;
      // Proceed when aligned or timed out (4s)
      if (fabsf(err) < 3.0f || el > 4000) {
        segPhase = SEG_FLY;
        segTimer = millis();
      }
      break;
    }

    case SEG_FLY: {
      // Pitch forward — time-based distance estimate
      // flyTime = dist / (speed * FLY_SPEED)
      unsigned long flyMs = (unsigned long)
                            (s.dist_m / (s.speed * FLY_SPEED) * 1000.0f);
      flyMs = constrain(flyMs, 500UL, 15000UL);
      sp_pitch = -14.0f * s.speed;   // negative = nose down = forward
      sp_roll  = 0;
      if (el > flyMs) {
        sp_pitch = 0;
        segPhase = SEG_PAUSE;
        segTimer = millis();
      }
      break;
    }

    case SEG_PAUSE:
      sp_roll=0; sp_pitch=0;
      if (el > 1500) {
        curSeg++;
        segPhase = SEG_TURN;
        segTimer = millis();
      }
      break;
  }
}

// ─────────────────────────────────────────────────────────────
//  TELEMETRY  (10 Hz)
// ─────────────────────────────────────────────────────────────
void sendTelemetry() {
  bat_mv_cached = (int)(analogRead(PIN_BATT) * BATT_SCALE);
  StaticJsonDocument<384> d;
  d["roll"]     = (int)(roll_cf  * 10) / 10.0;
  d["pitch"]    = (int)(pitch_cf * 10) / 10.0;
  d["yaw"]      = (int)(yaw_gyro * 10) / 10.0;
  d["alt_cm"]   = (int)alt_cm;
  d["bat_mv"]   = bat_mv_cached;
  d["mode"]     = MODE_NAME[mode];
  d["armed"]    = (mode > MODE_DISARMED && mode != MODE_KILL) ? 1 : 0;
  d["imu_ok"]   = imuOk  ? 1 : 0;
  d["sonar_ok"] = sonarStale ? 0 : 1;
  if (sonarStale) d["warn"] = "SONAR_STALE";
  String s; serializeJson(d, s);
  ESP_SERIAL.println(s);
}

// ─────────────────────────────────────────────────────────────
//  CONTROL LOOP  (250 Hz)
// ─────────────────────────────────────────────────────────────
void controlLoop(float dt) {

  // ── Read sensors ──────────────────────────────────────────
  if (imuOk) {
    mpuRead();
    computeAngles(dt);
  }

  // Sonar is read in the main loop at 25 Hz — NOT here.
  // pulseIn() is blocking (up to 23 ms) and would corrupt dt
  // for the gyro integration if called inside this timed loop.

  // ── DMS ───────────────────────────────────────────────────
  if (mode > MODE_DISARMED && mode != MODE_KILL) {
    if (millis() - lastCmdMs > DMS_TIMEOUT_MS) {
      DBG_SERIAL.println("[DMS ] TIMEOUT → FAILSAFE");
      mode = MODE_FAILSAFE;
    }
  }

  // ── Battery critical auto-LAND (checked at telemetry rate via bat_mv_cached) ──
  if (mode > MODE_DISARMED && mode != MODE_KILL &&
      mode != MODE_LAND    && mode != MODE_FAILSAFE) {
    if (bat_mv_cached > 0 && bat_mv_cached < BAT_CRIT_MV) {
      DBG_SERIAL.print(F("[BAT ] CRITICAL "));
      DBG_SERIAL.print(bat_mv_cached);
      DBG_SERIAL.println(F("mV -> auto LAND"));
      pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
      sp_roll=0; sp_pitch=0;
      landTimer = millis(); landCount = 0;
      mode = MODE_LAND;
    }
  }

  // ── Sonar stale warning (one-shot log — not every 250Hz tick) ────
  static bool sonarStaleLogged = false;
  if (sonarStale && !sonarStaleLogged) {
    sonarStaleLogged = true;
    DBG_SERIAL.println("[SONAR] STALE — altitude hold unreliable");
  }
  if (!sonarStale) sonarStaleLogged = false;

  // ── Mode logic ────────────────────────────────────────────
  switch (mode) {

    case MODE_DISARMED:
    case MODE_KILL:
      escsKill();
      return;                // skip PID

    case MODE_HOVER:
      // Hold level + current altitude — setpoints already set
      break;

    case MODE_OVERRIDE:
      // base_thr and setpoints set directly by GCS command
      break;

    case MODE_LAND:
    case MODE_FAILSAFE: {
      // Slowly lower target altitude: 12 cm/s
      static unsigned long lastDrop = 0;
      if (millis() - lastDrop > 83) {  // ~12Hz drop rate
        lastDrop     = millis();
        target_alt  -= 1.0f;
      }
      sp_roll=0; sp_pitch=0;
      // Landing detect: consecutive readings below 8cm
      if (alt_cm < 8.0f) {
        if (++landCount > 5) {
          mode = MODE_DISARMED;
          escsKill();
          return;
        }
      } else {
        landCount = 0;
      }
      break;
    }

    case MODE_RTL:
      // GPS RTL not implemented — notify GCS and fall back to LAND
      ack("RTL", false, "GPS RTL not implemented — initiating LAND");
      pidRoll.reset(); pidPitch.reset(); pidYaw.reset(); pidAlt.reset();
      sp_roll=0; sp_pitch=0;
      landTimer = millis(); landCount = 0;
      mode = MODE_LAND;
      break;

    case MODE_IMUMISSION:
      updateMission();
      break;
  }

  // ── PID ───────────────────────────────────────────────────
  float rOut = pidRoll.compute (sp_roll,   roll_cf,  dt);
  float pOut = pidPitch.compute(sp_pitch,  pitch_cf, dt);
  float yOut = pidYaw.compute  (sp_yaw,    yaw_gyro, dt);
  // Freeze altitude integrator while sonar is stale to prevent windup
  float savedAltInteg = pidAlt.integ;
  float aOut = pidAlt.compute  (target_alt, alt_cm,  dt);
  if (sonarStale) { pidAlt.integ = savedAltInteg; aOut = 0; }

  int thr = constrain(base_thr + (int)aOut, ESC_MIN, ESC_MAX - 200);

  motorMix(thr, rOut, pOut, yOut);
}

// ─────────────────────────────────────────────────────────────
//  READ UART
// ─────────────────────────────────────────────────────────────
void readUART() {
  while (ESP_SERIAL.available()) {
    char ch = (char)ESP_SERIAL.read();
    if (ch == '\n') {
      uartBuf[uartLen] = '\0';
      if (uartLen > 0) handleCmd(String(uartBuf));
      uartLen = 0;
    } else {
      if (uartLen < 255) {
        uartBuf[uartLen++] = ch;
      } else {
        uartLen = 0;   // line too long — discard and resync
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  DBG_SERIAL.begin(115200);
  ESP_SERIAL.begin(115200);
  DBG_SERIAL.println("\n══ SUDARSHAN FC v1.0 ══");

  // Pins
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  // Uno motor driver — Serial2 (TX=Pin16, RX=Pin17)
  // Uno runs ESC arming sequence internally and sends "READY" when done.
  UNO_SERIAL.begin(UNO_BAUD);
  DBG_SERIAL.println(F("[UNO ] waiting for motor driver (ESC arming ~3s)..."));
  {
    String line = "";
    bool   ready = false;
    unsigned long t0 = millis();
    while (millis() - t0 < 8000 && !ready) {
      while (UNO_SERIAL.available()) {
        char c = (char)UNO_SERIAL.read();
        if (c == '\n') {
          line.trim();
          if (line == "READY") ready = true;
          line = "";
        } else { line += c; }
      }
    }
    DBG_SERIAL.println(ready ? F("[UNO ] motor driver ready — ESCs armed") :
                               F("[UNO ] WARNING: motor driver not responding"));
  }

  // IMU — probe both addresses (AD0 LOW=0x68, AD0 HIGH=0x69)
  imuOk = mpuInit();
  if (!imuOk) {
    DBG_SERIAL.println("[IMU ] ERROR — MPU6050 not found at 0x68 or 0x69!");
    DBG_SERIAL.println("[IMU ] Check: SDA→Pin20 SCL→Pin21 VCC→3.3V GND common");
    DBG_SERIAL.println("[IMU ] FC continues — ARM is BLOCKED until IMU detected");
  } else {
    DBG_SERIAL.print(F("[IMU ] MPU6050 OK at 0x"));
    if (MPU < 0x10) DBG_SERIAL.print('0');
    DBG_SERIAL.println(MPU, HEX);
    mpuCalibrate();
  }

  // First sonar read — pre-init sonarValidMs so stale check doesn't fire on boot
  sonarValidMs = millis();
  alt_cm = readSonar();
  DBG_SERIAL.print(F("[SONAR] "));
  DBG_SERIAL.print(alt_cm, 1);
  DBG_SERIAL.println(F(" cm"));

  // PID init   ( Kp,   Ki,    Kd,   limit )
  pidRoll.init (1.8f, 0.05f, 0.80f, LIM_RP );
  pidPitch.init(1.8f, 0.05f, 0.80f, LIM_RP );
  pidYaw.init  (2.0f, 0.02f, 0.00f, LIM_YAW);  // Kd=0: yaw gyro noise would saturate derivative
  pidAlt.init  (3.0f, 0.10f, 1.50f, LIM_ALT);
  DBG_SERIAL.println("[PID ] initialized");

  lastCmdMs  = millis();
  lastLoopUs = micros();
  DBG_SERIAL.println("[READY] DISARMED — waiting for GCS\n");
}

// ─────────────────────────────────────────────────────────────
//  LOOP
// ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = micros();

  if (now - lastLoopUs >= LOOP_US) {
    float dt = (now - lastLoopUs) / 1000000.0f;
    // Cap dt: if something outside this block (e.g. UART handling or a
    // future blocking call) delays the loop, don't let a single huge dt
    // spike the gyro integration.
    if (dt > 0.010f) dt = 0.010f;
    lastLoopUs = now;
    loopCount++;

    controlLoop(dt);

    if (loopCount % TELEM_EVERY == 0)
      sendTelemetry();
  }

  // Sonar at ~25 Hz — separate from the 250Hz control loop so that
  // pulseIn's blocking time (up to 23ms) never corrupts dt above.
  static unsigned long lastSonarMs = 0;
  if (millis() - lastSonarMs >= 40) {
    lastSonarMs = millis();
    alt_cm = readSonar();
  }

  // UART reads happen between loop ticks (non-blocking)
  readUART();
}