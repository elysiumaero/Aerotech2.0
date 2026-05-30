# RADHA Protocol v1.0 — Full Reference

## Transport

- **Protocol:** TCP (raw socket)
- **Encoding:** UTF-8 JSON, newline-delimited (`\n`)
- **AP IP:** `192.168.4.1`
- **GCS Port:** `5760`
- **Phone Port:** `5762`

Each message is a single JSON object terminated with `\n`.  
No headers, no framing bytes, no length prefix — just JSON + newline.

---

## GCS → ESP32 → Mega2560

### ARM
Arms the drone. Saves home position. Resets all PIDs.
```json
{"cmd": "ARM"}
```
Prerequisites: drone must be in DISARMED mode, sitting level.

### DISARM
Disarms the drone. Cuts motors immediately.
```json
{"cmd": "DISARM"}
```

### HOVER
Stops all motion. Holds current altitude and heading.
```json
{"cmd": "HOVER"}
```

### LAND
Initiates slow descent. Auto-disarms on touchdown detection.
```json
{"cmd": "LAND"}
```

### KILL
**Emergency only.** Instantly cuts all motor signals. Drone will drop.
```json
{"cmd": "KILL"}
```

### PING
Heartbeat. Resets DMS timer on both ESP32 and FC. Not forwarded to FC.
```json
{"cmd": "PING"}
```
GCS sends this automatically every 1 second when connected.

### PRESET
Uploads and executes an autonomous IMU-based flight path.
```json
{
  "cmd": "PRESET",
  "segments": [
    {"bearing": 0.0,   "dist_m": 5.0, "speed": 0.5},
    {"bearing": 90.0,  "dist_m": 3.0, "speed": 0.3},
    {"bearing": 180.0, "dist_m": 5.0, "speed": 0.5},
    {"bearing": 270.0, "dist_m": 3.0, "speed": 0.3}
  ]
}
```
| Field | Type | Description |
|---|---|---|
| bearing | float | Absolute heading in degrees (0=North, 90=East) |
| dist_m | float | Distance to travel in metres |
| speed | float | Throttle factor 0.0–1.0 |

Max segments: 16. Each segment executes TURN → FLY → PAUSE (1.5s).

### OVERRIDE
Directly sets attitude setpoints and throttle. Used for manual control.
```json
{
  "cmd": "OVERRIDE",
  "roll": 5.0,
  "pitch": -3.0,
  "yaw": 0.0,
  "throttle": 1200
}
```
| Field | Type | Description |
|---|---|---|
| roll | float | Target roll in degrees (+right, -left) |
| pitch | float | Target pitch in degrees (+nose up, -nose down) |
| yaw | float | Target yaw in degrees (absolute) |
| throttle | int | Base throttle in µs (1000–1950) |

---

## Mega2560 → ESP32 → GCS

### Telemetry (10 Hz)
Sent automatically every 100ms when armed.
```json
{
  "roll":   1.2,
  "pitch": -0.5,
  "yaw":   182.3,
  "alt_cm": 45,
  "bat_mv": 11800,
  "mode":  "HOVER",
  "armed":  1
}
```
| Field | Type | Description |
|---|---|---|
| roll | float | Roll angle in degrees (-180 to +180) |
| pitch | float | Pitch angle in degrees (-90 to +90) |
| yaw | float | Yaw angle in degrees (-180 to +180) |
| alt_cm | int | Sonar altitude in centimetres |
| bat_mv | int | Battery voltage in millivolts |
| mode | string | Current flight mode name |
| armed | int | 1 = armed, 0 = disarmed |

### ACK (on command receipt)
```json
{"ack": "ARM",    "status": "OK"}
{"ack": "PRESET", "status": "ERR", "msg": "not armed"}
```

---

## Phone → ESP32 (Port 5762)

```json
{
  "lat":     28.613900,
  "lon":     77.209000,
  "alt":     215.0,
  "heading": 182.3,
  "baro_cm": 21500,
  "fix":     1,
  "sats":    8
}
```
| Field | Description |
|---|---|
| lat / lon | Decimal degrees |
| alt | GPS altitude in metres |
| heading | Compass heading 0–360° (0=North) |
| baro_cm | Barometric altitude in cm |
| fix | 1 = 3D GPS fix, 0 = no fix |
| sats | Number of satellites locked |

Recommended send rate: **1 Hz** for GPS, up to **5 Hz** for compass/baro.

---

## ESP32 → GCS Internal Events

```json
{"info": "GCS_CONNECTED"}
{"info": "PHONE_CONNECTED"}
{"info": "PHONE_DISCONNECTED"}
{"dms":  "FIRED", "action": "HOVER"}
{"type": "phone", "lat": 28.6139, "lon": 77.2090, ...}
```

---

## Timing Summary

| Direction | Rate | Purpose |
|---|---|---|
| GCS → ESP32 PING | 1 Hz | DMS keepalive |
| FC → GCS telem | 10 Hz | Live state |
| Phone → ESP32 | 1–5 Hz | GPS + sensors |
| ESP32 → FC GPS | 5 Hz | Navigation data |
| FC control loop | 250 Hz | PID execution |
| FC sonar read | 25 Hz | Altitude update |

---

## Error Handling

| Condition | Response |
|---|---|
| GCS disconnects | ESP32 DMS fires after 30s → HOVER sent to FC |
| FC gets no command | FC DMS fires after 30s → FAILSAFE (LAND) |
| Phone disconnects | GPS forwarding stops; FC keeps last known GPS |
| Bad JSON received | Silently discarded at all layers |
| ARM while armed | ACK ERR returned |
| PRESET while disarmed | ACK ERR returned |
