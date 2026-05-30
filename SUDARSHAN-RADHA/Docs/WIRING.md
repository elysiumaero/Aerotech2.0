# SUDARSHAN — Wiring Reference

> ⚠ Read completely before connecting anything. Wrong wiring will destroy components.

---

## 1. ESP32 ↔ Mega2560 UART

```
  Mega2560                          ESP32
  ─────────                         ─────────
  Pin 18 (TX1) ────[direct]───────► GPIO16 (RX2)    3.3V safe ✓
  Pin 19 (RX1) ◄───[DIVIDER]─────── GPIO17 (TX2)    5V → 3.3V ⚠
  GND          ────────────────────── GND            MUST be common
```

### Why a Voltage Divider?
Mega2560 TX outputs 5V logic. ESP32 GPIO inputs are **3.3V maximum**.
Without the divider, you will permanently damage the ESP32.
ESP32 TX → Mega RX is fine — 3.3V is enough to register as HIGH on Mega.

### Voltage Divider Circuit (5V → 3.3V)

```
  Mega Pin 18 (TX)
       │
      [10kΩ]
       │
       ├──────────────► ESP32 GPIO16 (RX2)
       │
      [20kΩ]
       │
      GND
```

Calculation: Vout = 5V × 20k / (10k + 20k) = **3.33V** ✓

**Components needed:** 1× 10kΩ resistor, 1× 20kΩ resistor (or two 10kΩ in series for the 20kΩ)

---

## 2. MPU6050 (IMU)

```
  Mega2560                 MPU6050
  ─────────                ────────
  Pin 20 (SDA) ───────────► SDA
  Pin 21 (SCL) ───────────► SCL
  3.3V         ───────────► VCC    ⚠ Use 3.3V NOT 5V
  GND          ───────────► GND
  GND          ───────────► AD0   (sets I2C address to 0x68)
```

> Keep I2C wires short (< 20cm). If MPU6050 not detected, add 4.7kΩ pull-ups from SDA/SCL to 3.3V.

---

## 3. HC-SR04 Sonar

```
  Mega2560                 HC-SR04
  ─────────                ────────
  D7           ───────────► TRIG
  D8           ───────────► ECHO   (5V output — safe for Mega directly)
  5V           ───────────► VCC
  GND          ───────────► GND
```

Range: 2cm – 400cm. Reliable below 200cm for landing.
Mount facing straight down, away from prop wash.

---

## 4. ESCs → Motors

```
  Mega2560 Pin        ESC              Motor Position
  ────────────        ───              ──────────────
  D3          ──────► FL ESC ──────►  Front-Left  (CW  prop ↺)
  D5          ──────► FR ESC ──────►  Front-Right (CCW prop ↻)
  D6          ──────► RL ESC ──────►  Rear-Left   (CCW prop ↻)
  D9          ──────► RR ESC ──────►  Rear-Right  (CW  prop ↺)
```

Each ESC connection:
```
  ESC Signal wire ──────► Mega pin (D3/D5/D6/D9)
  ESC GND wire    ──────► Mega GND    ← MANDATORY common ground
  ESC power (red) ──────► Battery distribution board
```

> ⚠ Never connect ESC power wires to Mega 5V rail. Power ESCs directly from battery.

### Motor Layout (Top View)

```
         FRONT
    FL(↺)     FR(↻)
      ╲         ╱
       ╲       ╱
        ●─────●
        │     │
        ●─────●
       ╱       ╲
      ╱         ╲
    RL(↻)     RR(↺)
         REAR

↺ = Clockwise prop (tighten counter-clockwise)
↻ = Counter-clockwise prop (tighten clockwise)
```

---

## 5. Battery Monitor

3S LiPo = 12.6V max. Mega ADC = 0–5V. Need voltage divider.

```
  Battery +
       │
      [47kΩ]
       │
       ├──────────────► Mega A0
       │
      [10kΩ]
       │
      GND
```

Calculation: Vout = 12.6V × 10k / (57k) = **2.21V** — safely within 5V ADC range.

Scale factor in firmware: `5000/1023 × 5.7 = 27.86 mV per ADC count`

---

## 6. Power Distribution

```
  3S LiPo (11.1V nominal / 12.6V full)
       │
  ┌────┴──────────────────────────────┐
  │           PDB / XT60              │
  ├───► ESC FL  ├───► ESC FR          │
  ├───► ESC RL  ├───► ESC RR          │
  └───► 5V BEC ─────► Mega2560 VIN    │
                └───► ESP32 VIN (5V)  │
```

> Use a 5V BEC (Battery Eliminator Circuit) from the PDB to power Mega and ESP32.  
> Do NOT power Mega from USB while ESCs are connected.

---

## 7. Full Pin Summary

| Pin | Connected To | Notes |
|---|---|---|
| D3 | FL ESC signal | PWM |
| D5 | FR ESC signal | PWM |
| D6 | RL ESC signal | PWM |
| D9 | RR ESC signal | PWM |
| D7 | HC-SR04 TRIG | Output |
| D8 | HC-SR04 ECHO | Input |
| D18 | ESP32 GPIO16 (via divider) | Serial1 TX |
| D19 | ESP32 GPIO17 | Serial1 RX |
| D20 | MPU6050 SDA | I2C |
| D21 | MPU6050 SCL | I2C |
| A0 | Battery divider output | ADC |
