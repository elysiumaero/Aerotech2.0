# SUDARSHAN — Bench Test Procedure

> **Props OFF for this entire document.**  
> Complete every section in order. Do not skip ahead.  
> Mark each item ✅ before moving to the next section.

---

## What You Need
- Laptop with RADHA GCS running
- Arduino IDE Serial Monitor (for Mega debug)
- Multimeter
- Android phone with Share GPS app
- 3S LiPo battery (charged)
- USB cables for Mega and ESP32 (testing phase)

---

## Section 1 — Hardware Inspection (Unpowered)

> Battery disconnected. USB disconnected. Props OFF.

```
[ ] Frame is rigid — no cracks, no loose arms
[ ] All 4 motors spin freely by hand (no grinding, no resistance)
[ ] Motor screws tight — no wobble when pulled
[ ] ESC wires not frayed, not touching each other
[ ] MPU6050 firmly seated — pins soldered or well-seated in socket
[ ] HC-SR04 mounted facing straight down
[ ] ESP32 and Mega mounted securely — no flex

WIRING CHECK:
[ ] Voltage divider installed between Mega Pin18 TX → ESP32 GPIO16 RX
[ ] Multimeter check on divider output:
    → Probe GND and divider mid-point
    → Inject 5V at input — should read ~3.3V at output
    → Actual reading: _______ V   (pass if 3.0–3.5V)
[ ] Common GND wire between ESP32 GND and Mega GND confirmed
[ ] ESP32 GPIO17 (TX) → Mega Pin19 (RX) — direct wire, no divider
[ ] MPU6050 VCC confirmed at 3.3V rail (NOT 5V)
[ ] HC-SR04 VCC at 5V rail
[ ] ESC signal wires: FL→D3, FR→D5, RL→D6, RR→D9
[ ] ESC GND signal wires connected to Mega GND
[ ] Battery divider: 47kΩ + 10kΩ → Mega A0
```

---

## Section 2 — ESP32 Power-On (USB only, battery disconnected)

```
[ ] Connect ESP32 via USB to laptop
[ ] Open Arduino IDE Serial Monitor → 115200 baud → select ESP32 port
[ ] Expected output:

    [UART ] Serial2 up @ 115200  RX=16  TX=17
    [WiFi ] AP OK  SSID: SUDARSHAN_AP  IP: 192.168.4.1
    [TCP  ] GCS   :5760   Phone :5762
    [READY] Waiting for GCS...

[ ] ESP32 LED is fast-blinking (125ms) — waiting for GCS
[ ] On laptop WiFi list: SUDARSHAN_AP visible
[ ] If output missing or garbled → re-flash ESP32 firmware
```

---

## Section 3 — Mega2560 Power-On (USB only, battery disconnected)

> Open a second Serial Monitor window for Mega (different COM port).

```
[ ] Connect Mega via USB to laptop
[ ] Open Serial Monitor → 115200 baud → select Mega port
[ ] Expected output:

    ══ SUDARSHAN FC v1.0 ══
    [ESC ] attached — holding ARM signal
    [ESC ] ready
    [IMU ] MPU6050 OK
    [IMU ] Calibrating — keep still...
    [IMU ] Offsets: X.XXX / X.XXX / X.XXX
    [SONAR] XX.X cm
    [PID ] initialized
    [READY] DISARMED — waiting for GCS

[ ] IMU calibration completes (keep drone still for ~2s)
[ ] Record IMU offsets: _____ / _____ / _____
[ ] If [IMU] ERROR → check MPU6050 SDA/SCL wiring and 3.3V power
[ ] Sonar reading makes sense (drone height from ground): _____cm
[ ] If sonar reads 0 → check D7/D8 wiring, HC-SR04 power
```

---

## Section 4 — GCS Connection Test

```
[ ] Connect laptop WiFi to SUDARSHAN_AP (password: radha2026)
[ ] Launch RADHA GCS → python radha_gcs.py
[ ] IP: 192.168.4.1   Port: 5760 → click CONNECT
[ ] GCS top bar shows: ● CONNECTED (cyan)
[ ] ESP32 Serial Monitor shows: [GCS  ] Connected from 192.168.4.2
[ ] ESP32 LED switches to slow pulse (500ms)
[ ] DMS countdown shows ~30s in GCS top bar
[ ] Wait 35 seconds without touching GCS:
    → DMS countdown reaches 0
    → GCS log shows: ⚠ DEAD-MAN SWITCH — sending HOVER
    → ESP32 Serial Monitor shows: [DMS  ] TIMEOUT — sending HOVER to FC
    → Mega Serial Monitor shows: [CMD] HOVER
[ ] Click HOVER in GCS to reset DMS ✓
```

---

## Section 5 — Telemetry Verification

```
[ ] GCS FLIGHT tab shows live values (not ---)
[ ] Roll reading: approximately 0° when drone level
[ ] Pitch reading: approximately 0° when drone level
[ ] Yaw reading: any value (gyro starts from 0 at boot)
[ ] Alt reading: matches approximate height from floor in cm

TILT TEST:
[ ] Tilt drone forward (nose down) → Pitch goes negative ✓
[ ] Tilt drone back  (nose up)     → Pitch goes positive ✓
[ ] Tilt drone right (right down)  → Roll goes positive  ✓
[ ] Tilt drone left  (left down)   → Roll goes negative  ✓
[ ] Rotate drone CW (top view)     → Yaw increases       ✓

If any axis responds backwards → check MPU6050 orientation / firmware axis mapping.

ATTITUDE INDICATOR:
[ ] Horizon line tilts with drone in GCS
[ ] Artificial horizon responds in real time (no lag > 0.5s)

ALTITUDE:
[ ] Wave hand under sonar → alt_cm decreases ✓
[ ] Remove hand → alt_cm returns to previous value ✓
```

---

## Section 6 — Battery Monitor

```
[ ] Connect 3S LiPo battery to PDB (NO ESC load — just power rails)
[ ] GCS bat_mv field shows a value
[ ] Measure battery with multimeter: _______ mV
[ ] GCS bat_mv reading: _______ mV
[ ] Acceptable error: < 300mV (resistor tolerance)
[ ] If reading is 0 → check A0 wiring and 47kΩ/10kΩ divider

Battery voltage reference:
    Full charge (3S):  12,600 mV
    Nominal   (3S):    11,100 mV
    Low alarm  (3S):   10,500 mV  ← land immediately
    Cutoff     (3S):    9,900 mV  ← never fly below this
```

---

## Section 7 — Command Test (Props OFF, Battery Connected)

> ESCs will beep during ARM. This is normal.  
> Motors will NOT spin at idle if ESC_IDLE is set correctly.

```
ARM:
[ ] Click ARM in GCS
[ ] Mega Serial Monitor: [CMD] ARM
[ ] ESCs beep arming sequence (2.5s)
[ ] GCS top bar: ARMED (green)
[ ] GCS mode: HOVER

HOVER:
[ ] Click HOVER in GCS
[ ] Mega Serial Monitor: [CMD] HOVER
[ ] GCS ACK log: ACK HOVER: OK

LAND:
[ ] Click LAND in GCS
[ ] Mega Serial Monitor: [CMD] LAND
[ ] GCS mode switches to LAND
[ ] GCS mode switches to DISARMED after ~3s (landing detect at 8cm)
[ ] Drone re-arms: click ARM again

KILL:
[ ] Click ⚠ KILL in GCS
[ ] Confirmation dialog appears ✓
[ ] Click YES
[ ] Mega Serial Monitor: [CMD] KILL
[ ] GCS mode: KILL
[ ] GCS arm status: DISARMED

OVERRIDE:
[ ] ARM drone again
[ ] Send OVERRIDE via Serial Monitor to Mega:
    {"cmd":"OVERRIDE","roll":0,"pitch":0,"yaw":0,"throttle":1050}
[ ] Mega Serial Monitor: [CMD] OVERRIDE
[ ] GCS mode: OVERRIDE
[ ] Click HOVER to return to normal ✓
[ ] DISARM
```

---

## Section 8 — Motor Direction Test (Battery + ESCs connected, Props OFF)

```
[ ] ARM from GCS
[ ] Slowly send increasing throttle via OVERRIDE (start 1100µs)
[ ] Confirm each motor spins in correct direction:

    Motor       Expected Direction    Actual (✓/✗)
    ─────────   ──────────────────    ────────────
    Front-Left  CW  (clockwise)       [ ]
    Front-Right CCW (counter-CW)      [ ]
    Rear-Left   CCW (counter-CW)      [ ]
    Rear-Right  CW  (clockwise)       [ ]

[ ] If any motor wrong direction → swap any 2 of its 3 phase wires → retest
[ ] DISARM after test
```

---

## Section 9 — Phone GPS Test

```
[ ] Connect phone to SUDARSHAN_AP WiFi (password: radha2026)
[ ] Open Share GPS app → TCP Client → 192.168.4.1:5762 → Start
[ ] ESP32 Serial Monitor: [PHONE] Connected from 192.168.4.3
[ ] GCS GPS panel updates:
    [ ] FIX shows 3D FIX (green) or NO FIX (red)
    [ ] SATS shows a number
    [ ] LAT / LON show decimal degree values
    [ ] HEADING shows degrees
[ ] Mega Serial Monitor shows GPS packets appearing:
    [CMD] GPS  lat=XX.XXXXXX  lon=XX.XXXXXX  fix=X  sats=X
[ ] Walk phone around room → lat/lon values change slowly ✓
[ ] Disconnect phone → GCS GPS panel freezes (last values held) ✓
[ ] ESP32 Serial Monitor: [PHONE] Connected... lost (no explicit disconnect msg)
```

---

## Section 10 — PRESET Path Test (No Flight)

```
[ ] In GCS PRESET tab, add a simple 3-segment path:
    Segment 1: Bearing 0°,   Dist 5m, Speed 0.5
    Segment 2: Bearing 90°,  Dist 5m, Speed 0.5
    Segment 3: Bearing 180°, Dist 5m, Speed 0.5

[ ] Preview shows correct L-shaped path on canvas ✓
[ ] ARM drone
[ ] Click EXECUTE PRESET
[ ] Mega Serial Monitor: [CMD] PRESET  3 segments
[ ] GCS ACK log: ACK PRESET: OK
[ ] GCS mode switches to IMUMISSION ✓
[ ] After ~30s drone returns to HOVER mode automatically ✓
[ ] DISARM
[ ] CLEAR ALL segments
```

---

## Bench Test Sign-Off

```
Tester name : ________________________________
Date        : ________________________________
Firmware versions:
    ESP32 Bridge : SUDARSHAN_Bridge v1.0
    Mega FC      : SUDARSHAN_FC     v1.0
    RADHA GCS    : RADHA GCS        v1.0

All sections passed:  YES / NO
Notes:
____________________________________________________________
____________________________________________________________

Cleared for prop fitting: YES / NO
```