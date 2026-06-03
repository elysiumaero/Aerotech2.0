/*
 * ╔══════════════════════════════════════════════════════════════╗
 * ║  SUDARSHAN MOTOR DRIVER — Arduino Uno / Nano                 ║
 * ║  Receives 10-byte motor packets from Mega FC via UART        ║
 * ║  Drives PCA9685 → 4 ESCs → 4 brushless motors               ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  WIRING                                                       ║
 * ║    Mega Pin 16 (TX2) ──── Uno Pin 0  (RX)                   ║
 * ║    Mega Pin 17 (RX2) ──── Uno Pin 1  (TX)                   ║
 * ║    Common GND (Mega GND ─── Uno GND)                        ║
 * ║    PCA9685  SDA → Uno A4  |  SCL → Uno A5                   ║
 * ║    PCA9685  VCC → Uno 5V  |  GND → Common GND               ║
 * ║    PCA9685  V+  → leave unconnected                          ║
 * ║    ESC signals: CH0=FL  CH1=FR  CH2=RL  CH3=RR              ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  PACKET FORMAT (10 bytes, sent by Mega at 250 Hz)            ║
 * ║    [0xAA][fl_H][fl_L][fr_H][fr_L][rl_H][rl_L][rr_H][rr_L][xor] ║
 * ║    xor = XOR of bytes 1..8 (checksum)                        ║
 * ╠══════════════════════════════════════════════════════════════╣
 * ║  STARTUP SEQUENCE                                             ║
 * ║    1. PCA9685 init                                            ║
 * ║    2. Hold ESC_ARM (1000 µs) for 2.5 s — ESC arming beeps   ║
 * ║    3. Send "READY\n" to Mega on Serial                       ║
 * ║  ⚠ Disconnect Pin 0/1 wires when uploading sketch via USB   ║
 * ╚══════════════════════════════════════════════════════════════╝
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ─────────────────────────────────────────────────────────────
//  CONFIG
// ─────────────────────────────────────────────────────────────
#define PCA_ADDR   0x40   // default; solder A0 pad to change
#define CH_FL      0
#define CH_FR      1
#define CH_RL      2
#define CH_RR      3

#define ESC_ARM    1000   // µs — minimum / arm signal
#define ESC_MIN    1050   // µs — minimum running throttle
#define ESC_MAX    1950   // µs — maximum throttle

#define PKT_START  0xAA
#define PKT_LEN    10

// ─────────────────────────────────────────────────────────────
//  GLOBALS
// ─────────────────────────────────────────────────────────────
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(PCA_ADDR);

uint8_t buf[PKT_LEN];
uint8_t idx = 0;

// ─────────────────────────────────────────────────────────────
//  ESC HELPERS
// ─────────────────────────────────────────────────────────────
void escKill() {
  pca.writeMicroseconds(CH_FL, ESC_ARM);
  pca.writeMicroseconds(CH_FR, ESC_ARM);
  pca.writeMicroseconds(CH_RL, ESC_ARM);
  pca.writeMicroseconds(CH_RR, ESC_ARM);
}

void escApply(uint16_t fl, uint16_t fr, uint16_t rl, uint16_t rr) {
  pca.writeMicroseconds(CH_FL, constrain(fl, ESC_MIN, ESC_MAX));
  pca.writeMicroseconds(CH_FR, constrain(fr, ESC_MIN, ESC_MAX));
  pca.writeMicroseconds(CH_RL, constrain(rl, ESC_MIN, ESC_MAX));
  pca.writeMicroseconds(CH_RR, constrain(rr, ESC_MIN, ESC_MAX));
}

// ─────────────────────────────────────────────────────────────
//  PACKET HANDLER
// ─────────────────────────────────────────────────────────────
void applyPacket() {
  // Verify XOR checksum over bytes 1..8
  uint8_t xorChk = 0;
  for (uint8_t i = 1; i < PKT_LEN - 1; i++) xorChk ^= buf[i];
  if (xorChk != buf[PKT_LEN - 1]) return;  // corrupted — discard silently

  uint16_t fl = ((uint16_t)buf[1] << 8) | buf[2];
  uint16_t fr = ((uint16_t)buf[3] << 8) | buf[4];
  uint16_t rl = ((uint16_t)buf[5] << 8) | buf[6];
  uint16_t rr = ((uint16_t)buf[7] << 8) | buf[8];

  // Kill packet (all ESC_ARM) → use escKill so constrain is bypassed
  if (fl == ESC_ARM && fr == ESC_ARM && rl == ESC_ARM && rr == ESC_ARM) {
    escKill();
  } else {
    escApply(fl, fr, rl, rr);
  }
}

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);   // UART to Mega (also USB — disconnect wires when flashing)

  pca.begin();
  pca.setOscillatorFrequency(27000000);  // actual osc ~27 MHz for accurate µs
  pca.setPWMFreq(50);                    // 50 Hz — standard ESC PWM
  delay(10);

  // ESC arming sequence: hold 1000 µs for 2.5 s
  escKill();
  delay(2500);

  // Signal Mega that ESCs are armed and ready
  Serial.println("READY");
}

// ─────────────────────────────────────────────────────────────
//  LOOP
// ─────────────────────────────────────────────────────────────
void loop() {
  while (Serial.available()) {
    uint8_t b = (uint8_t)Serial.read();

    if (idx == 0 && b != PKT_START) continue;  // hunt for start byte

    buf[idx++] = b;

    if (idx == PKT_LEN) {
      applyPacket();
      idx = 0;
    }
  }
}
