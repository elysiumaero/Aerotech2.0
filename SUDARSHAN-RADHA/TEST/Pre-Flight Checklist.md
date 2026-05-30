# SUDARSHAN — Pre-Flight Checklist

> Complete before **every** flight. No exceptions.  
> If any item fails → do not fly until resolved.

---

## PHASE 1 — Physical Inspection

> Battery disconnected. Drone on flat surface.

```
FRAME & MOTORS:
[ ] Frame arms tight — no flex when pressed
[ ] All 4 motors secure — no wobble when pulled laterally
[ ] Motor screws present and tight on all motors
[ ] Motor bells spin freely by hand — no grinding or resistance
[ ] No visible damage to frame, arms, or motor mounts

PROPS:
[ ] All 4 props fitted and tight
[ ] Correct orientation:
        Front-Left  → CW  prop (marked R or clockwise arrow)
        Front-Right → CCW prop (marked L or counter-clockwise arrow)
        Rear-Left   → CCW prop
        Rear-Right  → CW  prop
[ ] Props not cracked, chipped, or warped
[ ] Prop nuts/bolts tight — try to spin each prop by hand, should not loosen

WIRING:
[ ] No exposed copper wires near props or moving parts
[ ] ESC wires secured and not in prop arc path
[ ] No loose connectors — tug test each connector gently
[ ] Battery lead in good condition — no fraying near connector

ELECTRONICS:
[ ] ESP32 firmly mounted
[ ] Mega2560 firmly mounted
[ ] MPU6050 mount rigid — no flex or vibration risk
[ ] HC-SR04 facing straight down, unobstructed below
[ ] All mounting screws present (use thread-lock where applicable)
```

---

## PHASE 2 — Battery Check

```
[ ] Battery voltage measured with multimeter: _______ mV
[ ] Battery is above minimum flight voltage (10,500 mV for 3S)
[ ] Battery connector in good condition — no bent pins
[ ] Battery strap/mount secure — battery will not shift in flight
[ ] Battery balance lead protected from prop contact
[ ] Note cell count: ____S   Capacity: ____mAh
```

---

## PHASE 3 — Power-On Sequence

> Perform in this exact order.

```
STEP 1 — Power ESP32 (via BEC or USB for ground testing)
[ ] ESP32 LED fast-blinks → waiting for GCS ✓

STEP 2 — Power Mega2560 (via BEC, NOT USB in field)
[ ] No smoke, no burning smell
[ ] Serial Monitor (if connected): [READY] DISARMED ✓

STEP 3 — Connect battery to PDB
[ ] No spark on connection (small spark is normal — large spark is not)
[ ] No smoke, no heat from ESCs or PDB
[ ] All ESCs emit boot tones ✓

STEP 4 — Wait 5 seconds
[ ] IMU calibration completes — keep drone still during boot
[ ] No unusual sounds from motors
```

---

## PHASE 4 — GCS Connection

```
[ ] Laptop WiFi connected to: SUDARSHAN_AP
[ ] RADHA GCS launched → python radha_gcs.py
[ ] IP 192.168.4.1 Port 5760 → CONNECT
[ ] GCS status: ● CONNECTED (cyan) ✓
[ ] DMS countdown visible and counting down from 30s ✓

TELEMETRY LIVE CHECK:
[ ] Roll: ___°  (should be near 0° on flat surface)
[ ] Pitch: ___° (should be near 0° on flat surface)
[ ] Yaw: ___°   (any value)
[ ] Alt: ___ cm (should match approximate height from ground)
[ ] Battery: ___mV  (matches multimeter reading ± 300mV) ✓
[ ] Mode: DISARMED ✓
```

---

## PHASE 5 — Phone GPS

```
[ ] Phone connected to SUDARSHAN_AP WiFi
[ ] GPS Server by Metrologic → TCP Client → 192.168.4.1:5762 → NMEA → streaming
[ ] GCS GPS panel shows:
    [ ] LAT: __________ (not 0.000000)
    [ ] LON: __________ (not 0.000000)
    [ ] FIX: 3D FIX (green) ← do not fly with NO FIX
    [ ] SATS: ≥ 6 satellites ← minimum for navigation
    [ ] HEADING: ___°
[ ] GPS stable for at least 60 seconds before flight
[ ] Note GPS accuracy / satellite count: _______ sats
```

---

## PHASE 6 — Sensor Sanity Check

```
ATTITUDE:
[ ] Tilt drone forward slightly → Pitch goes negative ✓
[ ] Return to level → Pitch returns to ~0° ✓
[ ] If attitude not responding → DO NOT FLY → check IMU

SONAR:
[ ] Hold hand 20cm below drone → alt drops ✓
[ ] Remove hand → alt returns ✓
[ ] Sonar clear — no obstructions below drone on takeoff spot

BATTERY ALARM:
[ ] GCS bat_mv reading above 10,500mV ✓
[ ] If below 10,500mV → swap battery now
```

---

## PHASE 7 — Flight Area

```
ENVIRONMENT:
[ ] Open area — minimum 5m clearance in all directions
[ ] No people within 10m during takeoff and landing
[ ] Wind below 15 km/h (light breeze) — check weather app
[ ] No rain — electronics are NOT waterproofed
[ ] Ground flat and hard — grass, concrete, or asphalt
[ ] No obstacles in intended flight path
[ ] Note wind direction: _________  Speed: _______ km/h

OVERHEAD:
[ ] No overhead wires, trees, or structures within flight path
[ ] No other aircraft / drones in area
[ ] Daylight or good artificial lighting (no night flight)
```

---

## PHASE 8 — Emergency Procedures Briefing

> Review before every flight — especially with new operators.

```
EMERGENCY PROCEDURES (memorise these):
[ ] KILL button location confirmed in GCS — bottom of controls panel
[ ] LAND button location confirmed
[ ] If GCS disconnects → drone auto-HOVERs after 30s (DMS)
[ ] If drone goes out of control → press KILL immediately
[ ] If battery alarm fires → land immediately, do not continue flight
[ ] Abort if drone drifts > 3m from hover point on first flight
[ ] Never stand under or directly behind the drone

KILL ZONE (stand here):
    Always stand BEHIND and to the SIDE of the drone
    Never stand in the plane of the propellers
    Minimum safe distance: 5m from drone during armed state
```

---

## PHASE 9 — Pre-ARM Final Check

```
[ ] All previous phases passed
[ ] Drone placed on takeoff spot — level surface
[ ] Operator behind drone — clear line of sight to GCS
[ ] Second person standing by (recommended)
[ ] Throttle / OVERRIDE at minimum before ARM
[ ] DMS countdown reset (sent HOVER/PING recently)
[ ] GCS log is clear — no unexpected errors
[ ] Mode shows: DISARMED
[ ] Battery: _______ mV  (confirm one more time)
```

---

## ARM → TAKEOFF SEQUENCE

```
1. [ ] Click ARM in GCS → ESCs beep → mode shows HOVER
2. [ ] Wait 3 seconds — listen for any abnormal motor sounds
3. [ ] Slowly increase throttle via OVERRIDE
4. [ ] At first liftoff (10–20cm):
        [ ] Drone stable — no violent oscillations
        [ ] No spinning / yaw drift > 15°
        [ ] No tilting > 20° without correction
5. [ ] If unstable → LAND or KILL immediately
6. [ ] If stable → proceed to desired altitude
7. [ ] Hover at 50cm for 30s before any autonomous mission
```

---

## POST-FLIGHT CHECKLIST

```
IMMEDIATELY AFTER LANDING:
[ ] DISARM from GCS
[ ] Disconnect battery within 60s of landing (LiPo heat management)
[ ] Check battery voltage: _______ mV
    → If below 9,900mV → battery has been over-discharged (damaged)

INSPECTION AFTER FLIGHT:
[ ] Check all 4 motors for warmth — slightly warm is OK, hot is not
[ ] Check ESCs for heat — warm is OK, hot means over-current
[ ] Check props — any new cracks or chips? Replace if damaged
[ ] Check frame — any new cracks after flight?
[ ] Check all wire connections — vibration can loosen connectors
[ ] Check battery connector — any heat or discoloration?

LOG:
[ ] Note flight duration: _______ minutes
[ ] Note any anomalies observed:
    ____________________________________________________________
    ____________________________________________________________
[ ] GCS log saved / screenshotted if any errors occurred
[ ] Battery stored at storage voltage (11,100mV for 3S) if not flying again today
```

---

## Quick Reference — Status Indicators

| GCS Indicator | Meaning |
|---|---|
| ● CONNECTED (cyan) | ESP32 link active |
| ● DISCONNECTED (grey) | No ESP32 link |
| ARMED (green) | Motors can spin |
| DISARMED (red) | Motors safe |
| DMS < 8s (red) | Send any command now |
| GPS: 3D FIX (green) | GPS usable for navigation |
| GPS: NO FIX (red) | Do not attempt autonomous flight |
| Mode: FAILSAFE | DMS fired — landing automatically |
| Mode: KILL | Motors cut — drone unpowered |

| Battery (3S) | Status |
|---|---|
| > 12,000 mV | Full ✓ |
| 11,100 mV | Nominal ✓ |
| 10,500 mV | Low — land now ⚠ |
| < 9,900 mV | Critical — never fly ✗ |