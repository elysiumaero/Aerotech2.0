/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║       SUDARSHAN FC — Arduino Mega2560 v1.0                  ║
 * ║       Project : RADHA / SUDARSHAN UAV                       ║
 * ║       Loop    : 250Hz control  |  10Hz telemetry            ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  WIRING                                                      ║
 * ║    MPU6050  SDA → Pin 20  |  SCL → Pin 21   (I2C)           ║
 * ║    HC-SR04  Trig → D7     |  Echo → D8                      ║
 * ║    ESC FL→D3  FR→D5  RL→D6  RR→D9                          ║
 * ║    Battery  → A0  (via divider: 47kΩ + 10kΩ for 3S)        ║
 * ║    ESP32 TX → Pin 19 (Serial1 RX)                           ║
 * ║    ESP32 RX → Pin 18 (Serial1 TX)  [3.3V safe, no divider] ║
 * ║    ⚠ Update ESP32 firmware wiring to pins 18/19 on Mega     ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  LIBRARIES                                                   ║
 * ║    Wire.h · Servo.h · ArduinoJson v6                        ║
 * ╚══════════════════════════════════════════════════════════════╝
 */

#include <Wire.h>
#include <Servo.h>
#include <ArduinoJson.h>

// ─────────────────────────────────────────────────────────────
//  CONFIG
// ─────────────────────────────────────────────────────────────

// Serials
#define ESP_SERIAL   Serial1   // pins 18(TX) / 19(RX) — to ESP32
#define DBG_SERIAL   Serial    // USB debug

// ESC pins
#define PIN_FL  3
#define PIN_FR  5
#define PIN_RL  6
#define PIN_RR  9

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

// ESCs
Servo escFL, escFR, escRL, escRR;

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

// UART receive buffer
String uartBuf = "";

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
  for (uint8_t addr : {(uint8_t)0x68, (uint8_t)0x69}) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) { MPU = addr; break; }
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
  DBG_SERIAL.printf("[IMU ] Offsets: %.3f / %.3f / %.3f\n",
                    gyrCal[0], gyrCal[1], gyrCal[2]);
}

void computeAngles(float dt) {
  float aRoll  =  atan2f(accY, accZ)                        * 57.2958f;
  float aPitch = atan2f(-accX, sqrtf(accY*accY + accZ*accZ)) * 57.2958f;
  roll_cf   = CF_ALPHA*(roll_cf  + gyrX*dt) + (1-CF_ALPHA)*aRoll;
  pitch_cf  = CF_ALPHA*(pitch_cf + gyrY*dt) + (1-CF_ALPHA)*aPitch;
  yaw_gyro += (IMU_YAW_SIGN * gyrZ) * dt;
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
    // EMA: blend 40% new reading into 60% running value — rejects single spikes
    // while tracking real altitude changes within a few readings.
    return alt_cm * 0.60f + raw * 0.40f;
  }
  if (millis() - sonarValidMs > 500) sonarStale = true;
  return alt_cm;               // hold last valid value
}

// ─────────────────────────────────────────────────────────────
//  ESCs
// ─────────────────────────────────────────────────────────────
void escsWrite(int fl, int fr, int rl, int rr) {
  escFL.writeMicroseconds(constrain(fl, ESC_MIN, ESC_MAX));
  escFR.writeMicroseconds(constrain(fr, ESC_MIN, ESC_MAX));
  escRL.writeMicroseconds(constrain(rl, ESC_MIN, ESC_MAX));
  escRR.writeMicroseconds(constrain(rr, ESC_MIN, ESC_MAX));
}

void escsKill() {
  escFL.writeMicroseconds(ESC_ARM);
  escFR.writeMicroseconds(ESC_ARM);
  escRL.writeMicroseconds(ESC_ARM);
  escRR.writeMicroseconds(ESC_ARM);
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
  escsWrite(
    thr + (int)( p + r - y),   // FL
    thr + (int)( p - r + y),   // FR
    thr + (int)(-p + r + y),   // RL
    thr + (int)(-p - r - y)    // RR
  );
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
    escsArm();
    mode = MODE_HOVER;
    ack("ARM", true);
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
    // Slow compass correction to cancel long-term gyro yaw drift
    if (gps_fix) {
      float diff = gps_hdg - yaw_gyro;
      while (diff >  180) diff -= 360;
      while (diff < -180) diff += 360;
      yaw_gyro += 0.005f * diff;  // very slow weight — won't disturb yaw PID
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
    // Arm all ESCs to minimum first
    escsKill();
    delay(500);
    // Spin only the requested motor
    if      (!strcmp(motor, "FL")) escFL.writeMicroseconds(thr);
    else if (!strcmp(motor, "FR")) escFR.writeMicroseconds(thr);
    else if (!strcmp(motor, "RL")) escRL.writeMicroseconds(thr);
    else if (!strcmp(motor, "RR")) escRR.writeMicroseconds(thr);
    else { ack("MOTOR_TEST", false, "bad motor"); return; }
    delay(dur);        // blocking OK — drone is DISARMED on bench
    escsKill();
    ack("MOTOR_TEST", true, motor);
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
      segs[segCount++] = {
        s["bearing"] | 0.0f,
        s["dist_m"]  | 1.0f,
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
  StaticJsonDocument<256> d;
  d["roll"]   = (int)(roll_cf  * 10) / 10.0;
  d["pitch"]  = (int)(pitch_cf * 10) / 10.0;
  d["yaw"]    = (int)(yaw_gyro * 10) / 10.0;
  d["alt_cm"] = (int)alt_cm;
  d["bat_mv"] = bat_mv_cached;
  d["mode"]   = MODE_NAME[mode];
  d["armed"]  = (mode > MODE_DISARMED && mode != MODE_KILL) ? 1 : 0;
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
      DBG_SERIAL.printf("[BAT ] CRITICAL %.0fmV → auto LAND\n", (float)bat_mv_cached);
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
  float aOut = pidAlt.compute  (target_alt, alt_cm,  dt);

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
      uartBuf.trim();
      if (uartBuf.length() > 0) handleCmd(uartBuf);
      uartBuf = "";
    } else {
      uartBuf += ch;
      if (uartBuf.length() > 512) uartBuf = "";
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

  // ESC attach + arm sequence (sends ESC_ARM for 2.5s)
  escFL.attach(PIN_FL); escFR.attach(PIN_FR);
  escRL.attach(PIN_RL); escRR.attach(PIN_RR);
  escsKill();
  DBG_SERIAL.println("[ESC ] attached — holding ARM signal");
  delay(2500);
  DBG_SERIAL.println("[ESC ] ready");

  // IMU — probe both addresses (AD0 LOW=0x68, AD0 HIGH=0x69)
  imuOk = mpuInit();
  if (!imuOk) {
    DBG_SERIAL.println("[IMU ] ERROR — MPU6050 not found at 0x68 or 0x69!");
    DBG_SERIAL.println("[IMU ] Check: SDA→Pin20 SCL→Pin21 VCC→3.3V GND common");
    DBG_SERIAL.println("[IMU ] FC continues — ARM is BLOCKED until IMU detected");
  } else {
    DBG_SERIAL.printf("[IMU ] MPU6050 OK at 0x%02X\n", MPU);
    mpuCalibrate();
  }

  // First sonar read
  alt_cm = readSonar();
  sonarValidMs = millis();   // prevent premature stale flag on boot
  DBG_SERIAL.printf("[SONAR] %.1f cm\n", alt_cm);

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