# SUDARSHAN Setup Guide — End to End

Complete first-time setup from nothing to first hover.

---

## Prerequisites

### Software
- Python 3.8 or later — https://python.org
- Arduino IDE 2.x — https://arduino.cc/en/software
- ESP32 board package installed in Arduino IDE
- ArduinoJson v6 library installed in Arduino IDE

### Hardware
- Arduino Mega2560
- ESP32 DevKit (30-pin or 38-pin)
- MPU6050 breakout module
- HC-SR04 ultrasonic sonar
- 4× ESCs (rated for your motors)
- 4× 1900KV brushless motors
- 3S LiPo battery + XT60 connector
- 5V BEC or UBEC (3A minimum)
- Power distribution board (PDB)
- Resistors: 10kΩ × 2, 20kΩ × 1, 47kΩ × 1
- Jumper wires, breadboard or PCB for dividers

---

## Part 1 — Install Arduino IDE Dependencies

### Add ESP32 Board Package
1. Arduino IDE → File → Preferences
2. Additional Boards Manager URLs — add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Tools → Board → Boards Manager → search `esp32` → install by Espressif

### Install ArduinoJson
1. Tools → Manage Libraries
2. Search `ArduinoJson`
3. Install version 6.x by Benoit Blanchon

---

## Part 2 — Flash ESP32

1. Open `ESP32/SUDARSHAN_Bridge/SUDARSHAN_Bridge.ino`
2. Tools → Board → ESP32 Dev Module
3. Tools → Port → select your ESP32 COM port
4. Tools → Upload Speed → 115200
5. Click Upload
6. Open Serial Monitor (115200 baud)
7. You should see:
   ```
   [UART ] Serial2 up @ 115200  RX=16  TX=17
   [WiFi ] AP OK  SSID: SUDARSHAN_AP  IP: 192.168.4.1
   [TCP  ] GCS   :5760   Phone :5762
   [READY] Waiting for GCS...
   ```
8. ESP32 LED fast-blinks = waiting for GCS ✓

---

## Part 3 — Flash Arduino Mega2560

1. Open `FC/SUDARSHAN_FC/SUDARSHAN_FC.ino`
2. Tools → Board → Arduino Mega or Mega 2560
3. Tools → Processor → ATmega2560
4. Tools → Port → select Mega COM port
5. Click Upload
6. Open Serial Monitor (115200 baud)
7. You should see:
   ```
   ══ SUDARSHAN FC v1.0 ══
   [ESC ] attached — holding ARM signal
   [ESC ] ready
   [IMU ] MPU6050 OK
   [IMU ] Calibrating — keep still...
   [IMU ] Offsets: 0.xxx / 0.xxx / 0.xxx
   [SONAR] XX.X cm
   [PID ] initialized
   [READY] DISARMED — waiting for GCS
   ```
8. If you see `[IMU ] ERROR` — check MPU6050 wiring

> During calibration the drone must be completely still for ~2 seconds.

---

## Part 4 — Wire Everything

Follow `/Docs/WIRING.md` exactly. Build in this order:

1. Voltage divider first (test with multimeter before connecting to ESP32)
2. ESP32 ↔ Mega2560 UART (GPIO17→Pin19, GPIO16→Pin18 via divider)
3. MPU6050 → Mega (SDA/SCL/3.3V/GND)
4. HC-SR04 → Mega (D7/D8/5V/GND)
5. ESC signal wires → Mega (D3/D5/D6/D9) + common GND
6. Battery divider → A0

**Before connecting battery:**
- Verify common GND between ESP32 and Mega
- Verify 3.3V on divider output with multimeter (should be ~3.3V)
- Verify MPU6050 VCC is 3.3V not 5V

---

## Part 5 — Run RADHA GCS

```bash
# Navigate to GCS folder
cd GCS

# Run (tkinter ships with Python, no pip needed)
python radha_gcs.py
```

GCS window opens. You should see `● DISCONNECTED` in top bar.

---

## Part 6 — First Connection Test

1. Power on ESP32 (USB or BEC)
2. Power on Mega2560 (USB for testing — NOT while ESCs connected)
3. On laptop: connect WiFi to `SUDARSHAN_AP` (password: `radha2026`)
4. In RADHA GCS: IP = `192.168.4.1`, Port = `5760`, click CONNECT
5. GCS shows `● CONNECTED`
6. ESP32 LED switches from fast blink to slow pulse

**Verify telemetry:**
- Roll/Pitch/Yaw should show values (not ---)
- Tilt the Mega by hand — angles should respond
- Mode shows `DISARMED`

---

## Part 7 — ESC Calibration

**Do this once before first flight. Props OFF. Battery connected.**

ESC calibration sets the throttle range (1000–2000µs) in each ESC.

1. Disconnect battery
2. Set `ESC_IDLE = 1950` temporarily in firmware (max throttle signal)
3. Flash Mega
4. Connect battery while holding ESC calibration button if your ESCs have one
5. Wait for high-pitched beeps (max throttle recognized)
6. Set `ESC_IDLE = 1000` (min throttle), re-flash
7. Wait for low beeps (min throttle recognized) — calibration done
8. Set `ESC_IDLE = 1150` (actual idle), re-flash

> Calibration procedure varies by ESC brand. Check your ESC manual.

---

## Part 8 — Motor Direction Check

**Props OFF. Battery connected. ESCs calibrated.**

1. ARM from GCS
2. Slowly increase throttle via OVERRIDE command
3. Check each motor spins in correct direction:

```
    Front-Left  → Clockwise (CW)   ↺
    Front-Right → Counter-CW (CCW) ↻
    Rear-Left   → Counter-CW (CCW) ↻
    Rear-Right  → Clockwise (CW)   ↺
```

4. If a motor spins wrong: swap any 2 of its 3 phase wires
5. DISARM after check

---

## Part 9 — Phone GPS Setup

1. Install **Share GPS** app (Android) or see `/Phone/README.md`
2. Connect phone to `SUDARSHAN_AP` WiFi
3. Configure TCP client:
   - Server: `192.168.4.1`
   - Port: `5762`
4. Start sending GPS data
5. RADHA GCS GPS panel should show lat/lon/fix
6. Mega Serial Monitor should show `[CMD] GPS` packets

---

## Part 10 — Bench Test (Props OFF)

Run through `/Tests/BENCH_TEST.md` completely.
All items must pass before fitting props.

---

## Part 11 — First Hover

**Open area. 5m clearance. Two people if possible.**

1. Fit props (double-check CW/CCW orientation!)
2. Place drone on flat ground
3. ARM from GCS
4. Monitor battery voltage in GCS
5. Slowly increase throttle via OVERRIDE
6. At first liftoff — immediately check for:
   - Stable attitude (not spinning)
   - No violent oscillations
7. If stable: hover at 30–50cm for 10 seconds
8. LAND from GCS
9. Review GCS log for anything unexpected

**Emergency:** KILL button in GCS cuts all motors instantly.

---

## Part 12 — First Preset Path

1. Build a simple square in PRESET tab:
   ```
   Bearing  0°,  Dist 3m, Speed 0.3
   Bearing 90°,  Dist 3m, Speed 0.3
   Bearing 180°, Dist 3m, Speed 0.3
   Bearing 270°, Dist 3m, Speed 0.3
   ```
2. ARM and take off manually via OVERRIDE to ~1m
3. Switch to HOVER to stabilize
4. Click EXECUTE PRESET
5. Monitor from GCS — be ready on LAND

---

## Troubleshooting Quick Reference

| Problem | Check |
|---|---|
| GCS won't connect | Laptop on SUDARSHAN_AP? Port 5760? ESP32 powered? |
| No telemetry | Mega flashed? UART divider correct? Common GND? |
| IMU error on boot | MPU6050 on 3.3V? SDA/SCL on pins 20/21? |
| Sonar reads 0 | D7/D8 wiring? HC-SR04 powered? |
| Motors don't arm | ESCs calibrated? DM3/D5/D6/D9 connected? |
| Drone flips | Motor direction? Prop direction? ESC pin assignment? |
| GPS not showing | Phone on SUDARSHAN_AP? Port 5762? JSON format correct? |
| DMS fires immediately | PING from GCS working? WiFi stable? |