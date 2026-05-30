# SUDARSHAN UAV — System Architecture

## Overview

SUDARSHAN is a fully autonomous quadcopter UAV controlled by the RADHA Ground Control Station (GCS). The system uses a three-layer hardware stack with a phone as an external sensor provider.

---

## Full System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        OPERATOR                                  │
│                           │                                      │
│               ┌───────────▼────────────┐                        │
│               │     LAPTOP (GCS)       │                        │
│               │   RADHA GCS v1.0       │                        │
│               │   Python / Tkinter     │                        │
│               │                        │                        │
│               │  ┌──────────────────┐  │                        │
│               │  │  FLIGHT Tab      │  │                        │
│               │  │  PRESET Tab      │  │                        │
│               │  │  Telemetry Panel │  │                        │
│               │  │  GPS Panel       │  │                        │
│               │  │  Attitude Ind.   │  │                        │
│               │  │  Dead-Man Switch │  │                        │
│               │  └──────────────────┘  │                        │
│               └────────────┬───────────┘                        │
│                            │ TCP Port 5760                       │
│                            │ JSON over WiFi                      │
│                            │                                     │
│   ┌───────────┐            │            ┌──────────────────┐    │
│   │   PHONE   │            │            │    ESP32 WiFi AP │    │
│   │  Android  │────────────┼───────────►│  SUDARSHAN_AP    │    │
│   │           │ TCP :5762  │            │  192.168.4.1     │    │
│   │ GPS       │            │            │                  │    │
│   │ Baro      │            └───────────►│  Port 5760 (GCS) │    │
│   │ Compass   │                         │  Port 5762 (PHN) │    │
│   └───────────┘                         │                  │    │
│                                         │  DMS 30s timer   │    │
│                                         └────────┬─────────┘    │
│                                                  │ UART Serial  │
│                                                  │ 115200 baud  │
│                                                  │ GPIO16/17    │
│                                         ┌────────▼─────────┐    │
│                                         │  ARDUINO MEGA    │    │
│                                         │    2560 FC       │    │
│                                         │                  │    │
│                                         │  MPU6050 (IMU)   │    │
│                                         │  HC-SR04 (sonar) │    │
│                                         │  Battery (A0)    │    │
│                                         │  250Hz loop      │    │
│                                         │  CF filter       │    │
│                                         │  PID controller  │    │
│                                         └──┬──┬──┬──┬──────┘    │
│                                            │  │  │  │           │
│                              D3  ──────────┘  │  │  └──── D9   │
│                              D5  ─────────────┘  └──── D6      │
│                                                                  │
│                    ┌────┐  ┌────┐  ┌────┐  ┌────┐              │
│                    │ESC │  │ESC │  │ESC │  │ESC │              │
│                    │ FL │  │ FR │  │ RL │  │ RR │              │
│                    └──┬─┘  └──┬─┘  └──┬─┘  └──┬─┘              │
│                       │       │       │       │                  │
│                    ┌──┴─┐  ┌──┴─┐  ┌──┴─┐  ┌──┴─┐              │
│                    │MOT │  │MOT │  │MOT │  │MOT │              │
│                    │1900│  │1900│  │1900│  │1900│              │
│                    │ KV │  │ KV │  │ KV │  │ KV │              │
│                    └────┘  └────┘  └────┘  └────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Roles

### RADHA GCS (Laptop)
- Primary operator interface
- Sends flight commands over TCP
- Displays live telemetry from FC
- Displays GPS data from phone
- Runs dead-man switch (sends HOVER after 30s inactivity)
- Builds and executes preset flight paths

### ESP32 (WiFi AP Bridge)
- Broadcasts `SUDARSHAN_AP` WiFi network (no router needed)
- Accepts TCP connections from GCS (port 5760) and phone (port 5762)
- Relays GCS commands to FC over UART
- Relays FC telemetry back to GCS
- Merges phone GPS data and forwards to FC at 5Hz
- Mirrors phone data to GCS for display
- Runs its own 30s DMS as hardware backup

### Arduino Mega2560 (Flight Controller)
- Core flight computer running at 250Hz
- Reads MPU6050 IMU via I2C
- Applies complementary filter for roll/pitch/yaw
- Reads HC-SR04 sonar for altitude
- Runs PID loops for roll, pitch, yaw, altitude
- Executes all flight modes
- Sends telemetry to GCS at 10Hz

### Phone (GPS + Sensors)
- Provides GPS (lat/lon/alt/fix/sats)
- Provides compass heading
- Provides barometric altitude
- Connects directly to ESP32 AP on port 5762

---

## Data Flow

```
COMMAND FLOW (GCS → FC):
GCS ──JSON──► ESP32 ──UART──► Mega2560 ──► Motors

TELEMETRY FLOW (FC → GCS):
Mega2560 ──UART──► ESP32 ──JSON──► GCS Display

GPS FLOW (Phone → FC + GCS):
Phone ──JSON──► ESP32 ──(mirror)──► GCS GPS Panel
                    └──(5Hz)──UART──► Mega2560 FC

DEAD-MAN SWITCH:
GCS DMS: No PING 30s → send HOVER cmd → ESP32 → FC
ESP32 DMS: No GCS packet 30s → direct HOVER → FC (hardware backup)
FC DMS: No UART cmd 30s → FAILSAFE mode (independent)
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| GCS UI | Python 3.8+, Tkinter |
| GCS Comms | socket (TCP), threading, json |
| ESP32 Firmware | Arduino C++, WiFi.h, ArduinoJson v6 |
| FC Firmware | Arduino C++, Wire.h, Servo.h, ArduinoJson v6 |
| Protocol | Newline-delimited JSON over TCP |
| IMU Filter | Complementary filter (98% gyro / 2% accel) |
| Flight Control | PID (roll, pitch, yaw, altitude) |

---

## Flight Modes

| Mode | Description | Entry |
|---|---|---|
| DISARMED | Motors off, safe | Boot / DISARM cmd |
| HOVER | Level hold + altitude hold | ARM cmd |
| LAND | Slow descent, auto-disarm on touchdown | LAND cmd |
| RTL | Return to home (GPS required) | RTL cmd |
| OVERRIDE | Direct setpoints from GCS | OVERRIDE cmd |
| FAILSAFE | Same as LAND, triggered by DMS | 30s no command |
| KILL | Instant motor cut | KILL cmd |
| IMUMISSION | Autonomous preset path | PRESET cmd |

