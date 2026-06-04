# Changelog — SUDARSHAN UAV

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- GPS RTL implementation (requires dedicated GPS module on Mega)
- Position hold via optical flow or GPS
- Mission waypoints using GPS coordinates instead of IMU-only bearing
- OTA firmware update mechanism via ESP32
- Boot handshake / version sync between all three boards

---

## [1.2.0] — 2025-06-04

### Added — Features
- **Web GCS** on ESP32 port 80 — full ground control station in a phone browser; no laptop required
- **WebSocket telemetry push** on ESP32 port 81 at ~10 Hz; HTTP poll fallback when WS unavailable
- **Feature #12 — Altitude setpoint slider**: `ALT_HOLD` command (30–500 cm) in both web GCS and Python GCS
- **Feature #13 — PRESET path builder**: SVG tap canvas on phone; click-mode interactive canvas on laptop GCS
- **Feature #14 — WebSocket client** in web GCS with 3-second auto-reconnect
- **NAV tab** in Python GCS: compass canvas, bearing/distance calculator, FLY TO command
- **GUIDE tab** in Python GCS: live preflight checklist updated from telemetry; SIM LOCK blocks ARM in training
- **Priority lock**: Python laptop GCS has exclusive control; web GCS returns `{ok:0,locked:1}` when laptop connected
- Override codes: `1410` (session unlock), `980752` (master — all auth checks)
- KILL button on web GCS requires double-tap within 3 s (no `confirm()` dialog on mobile)
- DMS PING auto-sent every 25 s from web GCS JavaScript while browser tab is open

### Added — Security (v1.2.0) [SECURITY]
- **ESP32 command whitelist**: unknown command strings dropped before reaching FC UART
- **ESP32 rate limiter** on `/api/cmd`: minimum 150 ms between commands (~6/s max)
- **FC unknown command logging**: unrecognised commands logged to Serial and ACK'd ERR instead of silently ignored
- **FC FORCE_ARM double-confirm**: requires `"confirm":"FORCE_ARM"` field in JSON
- **FC MOTOR_TEST rate limit**: rejected if called within 5 s of previous test
- **FC CAL_ESC rate limit**: rejected if called within 10 s of previous calibration
- **FC OVERRIDE throttle slew rate**: maximum 50 µs change per command — prevents sudden full-throttle
- **Python GCS input sanitiser**: all outgoing command numeric fields clamped to safe hardware limits before transmission
- **Python GCS thread-safe state**: `self._armed` and `self._mode` protected by `threading.RLock`

### Fixed — Safety-Critical Bugs
- **Sonar EMA cold-start** (`SUDARSHAN_FC.ino`): `alt_cm` could be 0 on first read; ARM now sets `target_alt` to minimum 30 cm if sonar uninitialized
- **Motor mix asymmetric saturation** (`SUDARSHAN_FC.ino`): proportional scale-down of all motors when any exceeds `ESC_MAX`; attitude ratios preserved
- **UART receive buffer unbounded** (`SUDARSHAN_FC.ino`): `String` heap replaced with fixed `char[256]`; eliminates Mega heap fragmentation
- **GPS compass correction unbounded** (`SUDARSHAN_FC.ino`): single-step correction capped at ±0.5°; suppressed when sonar stale
- **Gyro spike before integration** (`SUDARSHAN_FC.ino`): gyrX/Y/Z clamped to ±250°/s before complementary filter
- **Altitude PID windup on stale sonar** (`SUDARSHAN_FC.ino`): integrator frozen and output zeroed while `sonarStale` is true
- **PRESET dist_m zero guard** (`SUDARSHAN_FC.ino`): floored to 0.1 m to prevent division-by-zero in `flyMs`
- **SET_MOTOR_MAP mid-flight** (`SUDARSHAN_FC.ino`): blocked unless in DISARMED mode
- **UART packet desync** (`SUDARSHAN_MOTOR_UNO.ino`): 10 ms per-packet timeout; `idx` resets if no byte received mid-packet
- **ESP32 DMS race at boundary** (`ATLAS_ESP32_Bridge_v2.ino`): `checkDMS()` suppressed for 200 ms after any received GCS byte
- **AES malloc silent plaintext fallback** (`ATLAS_ESP32_Bridge_v2.ino`): returns empty String on heap failure — never silently transmits plaintext
- **Python GCS seq gap false-positive**: large backward seq jump (ESP32 reboot) handled silently; `_last_seq` protected by `threading.Lock`
- **Preflight motor test ACK race**: `queue.Queue` replaces shared `_ack_result` variable
- **NAV FLY TO unrecognised by FC**: now builds proper `segments[]` PRESET instead of `{id:"NAV"}` variant

### Changed
- ESP32 header tribute updated: "In Loving Memory" changed to celebratory dedication to Neelrisham Singh
- `handleRoot()` now serves full web GCS page instead of GPS-only page

### Documentation
- Added `SUDARSHAN_PROJECT_REPORT.pdf` (15-section technical reference and onboarding guide)
- Added `gen_report.py` (ReportLab script to regenerate the PDF)
- Added this `CHANGELOG.md`
- Added `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`

---

## [1.1.0] — 2025-04

### Added
- ARM interlock: ARM button disabled until all critical preflight tests pass
- AES-128-CBC optional encryption on TCP GCS link (toggle `ENCRYPT_ENABLED` in credentials.py)
- HTTPS GPS server on port 8443 (self-signed TLS certificate for browser `navigator.geolocation`)
- `MOTOR_TEST` command for bench-testing individual ESCs without arming
- Motor-ID wizard: `SPIN_CH` + `SET_MOTOR_MAP` commands to identify and remap motor channels
- `FORCE_ARM` admin command bypasses IMU check
- `CAL_ESC` command for one-time ESC throttle-range calibration
- Battery critical auto-LAND at 9.9 V; warning at 10.5 V
- Telemetry sequence number for gap detection
- Login dialog with SHA-256 hashed credentials (`auth.json`)
- Inauguration mode: T-minus ceremonial countdown before first ARM
- Pre-flight hardware test suite in Python GCS (`PreflightRunner`)

### Fixed
- MPU6050 now probes both I2C addresses (0x68 and 0x69) automatically at boot
- Sonar stale flag correctly detects no-valid-reading window > 500 ms
- ESC oscillator frequency comment: do NOT call `setOscillatorFrequency()` on stock PCA9685 modules

---

## [1.0.0] — 2025-03

### Added — Initial Release
- Arduino Mega 2560 flight controller (`SUDARSHAN_FC.ino`)
  - 250 Hz control loop with complementary filter (CF_ALPHA = 0.98)
  - 4 independent PID loops: roll, pitch, yaw, altitude
  - X-frame motor mixing with ESC output
  - 8 flight modes: DISARMED, HOVER, LAND, RTL (stub), OVERRIDE, FAILSAFE, KILL, IMUMISSION
  - PRESET autonomous path: up to 16 bearing+distance segments, IMU-only navigation
  - 3-layer dead-man switch (GCS / ESP32 / FC, each 30 s)
  - Battery voltage monitoring on A0
- Arduino Uno motor driver (`SUDARSHAN_MOTOR_UNO.ino`)
  - 10-byte binary packet protocol from Mega at 250 Hz
  - XOR checksum validation
  - PCA9685 → 4 ESC PWM signals at 50 Hz
  - ESC arming sequence on boot (1000 µs for 2.5 s)
- ESP32 WiFi bridge (`ATLAS_ESP32_Bridge_v2.ino`)
  - WiFi AP: SUDARSHAN_AP at 192.168.4.1
  - TCP GCS server on port 5760
  - TCP phone GPS server on port 5762
  - NMEA sentence parsing ($GPGGA, $GPRMC, $GNGGA, $GNRMC)
  - GPS data forwarded to FC at 5 Hz
  - Backup DMS: 30 s no GCS → HOVER injected to FC
- Python GCS (`radha_gcs.py`)
  - Tkinter UI with FLIGHT and PRESET tabs
  - TCP connection manager with reconnect
  - Live telemetry: roll, pitch, yaw, altitude, battery, mode, GPS
  - Artificial horizon (attitude indicator) canvas
  - Dead-man switch client-side (30 s PING)
  - Preset path builder: bearing, distance, speed segments
  - Flight log to file
- Documentation: ARCHITECTURE.md, PROTOCOL.md, WIRING.md, SETUP_GUIDE.md, PID_TUNING.md
- Tests: BENCH_TEST.md, V1.2_FEATURE_TEST.md, Pre-Flight Checklist.md
- Python unit tests: test_protocol_parsing.py, test_connection_manager.py, test_dms.py
