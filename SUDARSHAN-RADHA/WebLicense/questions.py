"""
SUDARSHAN UAV — Operator Certification Questions
20 MCQs drawn from the official training curriculum.
Each question: id, section, text, options (a-d), correct (0-indexed).
"""

QUESTIONS = [
    # ── Section 1: Hardware & Wiring ─────────────────────────────
    {
        "id": 1, "section": "Hardware & Wiring",
        "text": "Which I²C address does the MPU6050 use when the AD0 pin is pulled LOW?",
        "options": ["0x40", "0x68", "0x69", "0x76"],
        "correct": 1,
    },
    {
        "id": 2, "section": "Hardware & Wiring",
        "text": "What is the purpose of the voltage divider on the Mega TX → ESP32 RX line?",
        "options": [
            "Boost 3.3 V to 5 V for the ESP32",
            "Convert the 5 V Mega TX signal to 3.3 V for the ESP32 RX pin",
            "Filter out high-frequency noise on the serial line",
            "Regulate the ESP32 power supply",
        ],
        "correct": 1,
    },
    {
        "id": 3, "section": "Hardware & Wiring",
        "text": "Which PCA9685 channel drives the Front-Right (FR) motor?",
        "options": ["CH 0", "CH 1", "CH 2", "CH 3"],
        "correct": 1,
    },
    {
        "id": 4, "section": "Hardware & Wiring",
        "text": "Why must the wires on Uno pins 0 and 1 be disconnected before uploading a sketch via USB?",
        "options": [
            "They carry too much current and will damage the USB chip",
            "They are shared with the USB-to-Serial chip used for flashing",
            "They would corrupt the PCA9685 I²C bus",
            "They interfere with the I²C clock",
        ],
        "correct": 1,
    },
    # ── Section 2: Flight Controller ─────────────────────────────
    {
        "id": 5, "section": "Flight Controller",
        "text": "At what rate does the Mega 2560 flight controller run its main control loop?",
        "options": ["50 Hz", "100 Hz", "200 Hz", "250 Hz"],
        "correct": 3,
    },
    {
        "id": 6, "section": "Flight Controller",
        "text": "The complementary filter coefficient CF_ALPHA = 0.98 means the filter trusts:",
        "options": [
            "98% accelerometer data and 2% gyro data",
            "98% gyro data and 2% accelerometer data",
            "98% sonar data and 2% gyro data",
            "A 98% sample rate reduction",
        ],
        "correct": 1,
    },
    {
        "id": 7, "section": "Flight Controller",
        "text": "The drone spins clockwise continuously even though no yaw command is given. What is the correct first fix?",
        "options": [
            "Increase the yaw PID integral gain (Ki)",
            "Swap the propellers on all four motors",
            "Change IMU_YAW_SIGN from 1 to −1 in the firmware",
            "Decrease CF_ALPHA to reduce gyro weighting",
        ],
        "correct": 2,
    },
    {
        "id": 8, "section": "Flight Controller",
        "text": "During LAND mode, the FC triggers automatic DISARM when sonar reads below 8 cm for how many consecutive counts?",
        "options": ["2", "4", "6", "10"],
        "correct": 2,
    },
    {
        "id": 9, "section": "Flight Controller",
        "text": "Which command is BLOCKED by the FC if the drone is already armed?",
        "options": ["HOVER", "OVERRIDE", "LAND", "SET_MOTOR_MAP"],
        "correct": 3,
    },
    # ── Section 3: Communications & Protocols ─────────────────────
    {
        "id": 10, "section": "Communications & Protocols",
        "text": "What format are motor commands sent in from the Mega FC to the Uno motor driver?",
        "options": [
            "JSON over UART at 9600 baud",
            "10-byte binary packet with XOR checksum at 115200 baud",
            "8-byte CAN bus frame",
            "PWM pulse widths over a single wire",
        ],
        "correct": 1,
    },
    {
        "id": 11, "section": "Communications & Protocols",
        "text": "On which TCP port does the Python laptop GCS connect to the ESP32?",
        "options": ["80", "81", "5760", "8080"],
        "correct": 2,
    },
    {
        "id": 12, "section": "Communications & Protocols",
        "text": "At what rate does the FC send telemetry JSON to the GCS?",
        "options": ["1 Hz", "5 Hz", "10 Hz", "25 Hz"],
        "correct": 2,
    },
    {
        "id": 13, "section": "Communications & Protocols",
        "text": "The XOR checksum in the 10-byte motor packet covers which bytes?",
        "options": [
            "All 10 bytes including the start byte",
            "Bytes 0 through 8",
            "Bytes 1 through 8 (the four motor values)",
            "Bytes 1 through 9",
        ],
        "correct": 2,
    },
    # ── Section 4: Safety & Emergency ────────────────────────────
    {
        "id": 14, "section": "Safety & Emergency Procedures",
        "text": "How many independent Dead-Man Switch (DMS) layers does the SUDARSHAN system have?",
        "options": ["1", "2", "3", "4"],
        "correct": 2,
    },
    {
        "id": 15, "section": "Safety & Emergency Procedures",
        "text": "What action does the FC take when its 30-second DMS timeout fires?",
        "options": [
            "Immediately cuts all motors (KILL)",
            "Sends a warning to the GCS and waits",
            "Enters FAILSAFE mode and begins a slow descent (LAND)",
            "Holds current altitude indefinitely",
        ],
        "correct": 2,
    },
    {
        "id": 16, "section": "Safety & Emergency Procedures",
        "text": "When battery voltage drops to 9.9 V on a 3S LiPo, the FC automatically:",
        "options": [
            "Shows a warning flag in telemetry only",
            "Reduces maximum throttle to 50%",
            "Triggers auto-LAND immediately",
            "Cuts all motors instantly",
        ],
        "correct": 2,
    },
    {
        "id": 17, "section": "Safety & Emergency Procedures",
        "text": "After a KILL command is sent, what must the operator do before the drone can fly again?",
        "options": [
            "Send a DISARM command followed by ARM",
            "Send a HOVER command to reset the FC",
            "Power-cycle the entire drone (KILL requires hardware restart)",
            "Press the physical reset button on the Mega",
        ],
        "correct": 2,
    },
    # ── Section 5: Operations ─────────────────────────────────────
    {
        "id": 18, "section": "Operations & Procedures",
        "text": "What is the correct hardware power-on sequence?",
        "options": [
            "Power ESP32 first, then Mega and Uno",
            "Power Mega and Uno first, wait for ESC arming beeps (~3 s), then power ESP32",
            "Power all components simultaneously",
            "Power phone first, then ESP32, then Mega",
        ],
        "correct": 1,
    },
    {
        "id": 19, "section": "Operations & Procedures",
        "text": "What must be done BEFORE running the MOTOR_TEST command?",
        "options": [
            "ARM the drone in HOVER mode",
            "Remove all propellers from the motors",
            "Connect the phone GPS feed",
            "Enable AES encryption on the GCS link",
        ],
        "correct": 1,
    },
    {
        "id": 20, "section": "Operations & Procedures",
        "text": "What minimum safety perimeter should be cleared of people and obstacles before arming outdoors?",
        "options": ["2 metres", "5 metres", "10 metres", "20 metres"],
        "correct": 2,
    },
]

PASS_SCORE   = 14   # 70% of 20
TOTAL        = len(QUESTIONS)
COOLDOWN_DAYS = 3
