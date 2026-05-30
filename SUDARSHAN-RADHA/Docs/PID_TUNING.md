# PID Tuning Guide — SUDARSHAN FC

> Do all tuning steps in order. Do not skip to step 4.  
> Always tune with a **fully charged battery**.

---

## Understanding the Control Loops

SUDARSHAN runs 4 independent PID controllers:

```
  ┌─────────────┬──────────────┬──────────────────────────────────┐
  │  PID        │  Input       │  Output                          │
  ├─────────────┼──────────────┼──────────────────────────────────┤
  │  Roll       │  roll_cf °   │  µs differential: FL/RL vs FR/RR │
  │  Pitch      │  pitch_cf °  │  µs differential: FL/FR vs RL/RR │
  │  Yaw        │  yaw_gyro °  │  µs differential: CW vs CCW      │
  │  Altitude   │  alt_cm      │  µs added to all 4 motors        │
  └─────────────┴──────────────┴──────────────────────────────────┘
```

### Complementary Filter
The IMU uses a complementary filter to fuse gyro and accelerometer:
```
angle = 0.98 × (angle + gyro × dt) + 0.02 × accel_angle
```
- Gyro: fast, no drift short-term, drifts long-term
- Accel: slow, noisy, but stable long-term
- CF gives best of both at low CPU cost

---

## Default PID Values

```cpp
pidRoll.init (1.8, 0.05, 0.80, 300)   // Kp, Ki, Kd, limit
pidPitch.init(1.8, 0.05, 0.80, 300)
pidYaw.init  (3.0, 0.02, 0.50, 120)
pidAlt.init  (3.0, 0.10, 1.50, 250)
```

---

## Step 1 — Find ESC_IDLE

**Props OFF. Drone on bench.**

1. Set `ESC_IDLE = 1050` in firmware
2. Flash and ARM from GCS
3. Slowly increase `ESC_IDLE` by 10µs steps, re-flash each time
4. Find the value where all 4 motors spin consistently and smoothly
5. That value + 50µs is your `ESC_IDLE`

Typical range for 1900KV motors: **1100–1200µs**

> Rule: Drone should just barely lift at `ESC_IDLE + altitude PID max output`.
> If it shoots up immediately, ESC_IDLE is too high.

---

## Step 2 — Tune Roll and Pitch (Kp first)

**Props ON. Drone tethered (tie string from above, slack of ~30cm).**

Set all Ki and Kd to 0 first:
```cpp
pidRoll.init (X, 0.0, 0.0, 300)   // only tune Kp
pidPitch.init(X, 0.0, 0.0, 300)
```

### Kp Tuning
Start at `Kp = 0.5`. Increase by 0.3 each test.

| Symptom | Action |
|---|---|
| Drone barely responds to tilt | Kp too low → increase |
| Drone oscillates slowly (< 2Hz) | Kp slightly high → reduce by 0.2 |
| Drone oscillates fast (> 5Hz) | Kp way too high → halve it |
| Drone holds level, minor wobble | Kp is in range → move to Kd |

Target: drone holds level, twitches quickly back when pushed, no sustained oscillation.

### Kd Tuning
Once Kp is stable, add Kd starting at `0.3`. Increase by 0.2 each test.

| Symptom | Action |
|---|---|
| Oscillation from Kp now dampened | Kd working correctly |
| High-frequency vibration / buzzing motors | Kd too high → reduce by 0.1 |
| Drone feels sluggish to respond | Kd too high |

### Ki Tuning
Add Ki last. Start at `0.02`. It fixes steady-state drift (drone slowly drifting one direction).

| Symptom | Action |
|---|---|
| Drone slowly drifts one direction on hover | Ki too low |
| Drone oscillates slowly and diverges | Ki too high → halve it |
| Drone holds position well | Ki is correct |

---

## Step 3 — Tune Yaw (Kp first)

Yaw is controlled by differential speed between CW and CCW motors.

```cpp
pidYaw.init(X, 0.0, 0.0, 120)
```

Start at `Kp = 2.0`. Increase by 0.5 each test.

| Symptom | Action |
|---|---|
| Drone spins slowly and doesn't hold heading | Kp too low |
| Drone snaps to heading quickly | Good |
| Drone oscillates yaw left-right | Kp too high |

Yaw rarely needs Ki. Kd of `0.3–0.5` helps damp overshoot.

---

## Step 4 — Tune Altitude Hold

Altitude PID uses sonar (HC-SR04). Tune on a smooth flat surface.

```cpp
pidAlt.init(X, 0.0, 0.0, 250)
```

Start at `Kp = 2.0`.

| Symptom | Action |
|---|---|
| Drone descends slowly at hover | Kp too low |
| Drone bobs up-down slowly | Kp slightly high |
| Drone oscillates height rapidly | Kp too high |
| Drone holds height but drifts slowly up/down | Add Ki = 0.05 |
| Drone overshoots on altitude change | Add Kd = 0.5 |

---

## Step 5 — Free Hover

Remove tether. First free hover:
1. Arm in an open area (5m clearance all around)
2. Take off slowly — be ready on LAND button
3. If drone drifts: small trim on sp_roll / sp_pitch in firmware
4. Hover for 30 seconds watching for oscillations
5. Land, review GCS log for any anomalies

---

## PID Quick Reference Card

```
Roll / Pitch:
  Kp: 1.5 – 2.5   (start: 1.8)
  Ki: 0.02 – 0.1  (start: 0.05)
  Kd: 0.5 – 1.2   (start: 0.80)

Yaw:
  Kp: 2.0 – 4.0   (start: 3.0)
  Ki: 0.0 – 0.05  (start: 0.02)
  Kd: 0.2 – 0.6   (start: 0.50)

Altitude:
  Kp: 2.0 – 4.0   (start: 3.0)
  Ki: 0.05 – 0.15 (start: 0.10)
  Kd: 1.0 – 2.0   (start: 1.50)
```

---

## Common Problems

| Problem | Likely Cause | Fix |
|---|---|---|
| Flips on takeoff | Wrong motor rotation or props | Check motor direction vs diagram |
| One arm always low | ESC not calibrated | Recalibrate all ESCs to same range |
| Oscillates only when moving | Kd too low | Increase Kd by 0.2 |
| Oscillates at hover | Kp too high | Reduce Kp by 0.3 |
| Yaws continuously | Gyro Z not calibrated | Keep still during boot calibration |
| Height slowly drops | Ki too low in alt PID | Increase Ki by 0.02 |
| Jittery motors | Kd too high or electrical noise | Reduce Kd, add capacitors on ESC power |


