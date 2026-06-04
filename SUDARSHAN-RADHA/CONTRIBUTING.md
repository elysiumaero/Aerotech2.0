# Contributing to SUDARSHAN / RADHA Project

Thank you for your interest in contributing to the SUDARSHAN UAV project. This document explains how
to participate effectively and safely. Please read it in full before opening a pull request.

---

## Project Philosophy

SUDARSHAN is a real-flying UAV. Every line of code that reaches the flight controller (FC) or motor
driver has the potential to damage hardware or injure people. Our guiding principles are:

1. **Safety first, always.** No feature, optimization, or convenience improvement justifies weakening
   any safety mechanism.
2. **No untested changes to FC or motor firmware.** All changes to the Mega FC or Uno motor-driver
   sketches must be bench-tested with propellers removed before any pull request is opened.
3. **Conservative defaults.** When in doubt, fail safe. An unexpected LAND or DISARM is always
   preferable to an unexpected flight maneuver.
4. **Traceability.** Every non-trivial change must reference an issue number or a documented design
   decision. Reviewers must be able to understand *why* a change was made, not just *what* changed.

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork via GitHub UI, then:
git clone https://github.com/<your-username>/SUDARSHAN-RADHA.git
cd SUDARSHAN-RADHA
git remote add upstream https://github.com/sudarshan-radha/SUDARSHAN-RADHA.git
```

### 2. Branch Naming

Create a branch from `main` using one of the following prefixes:

| Prefix    | When to use                                              |
|-----------|----------------------------------------------------------|
| `feat/`   | New feature or capability                                |
| `fix/`    | Bug fix                                                  |
| `docs/`   | Documentation-only change                                |
| `test/`   | New or updated tests with no production code change      |
| `refactor/` | Code restructuring with no behaviour change            |
| `chore/`  | Build system, dependency, or tooling change              |

Examples:

```bash
git checkout -b feat/websocket-telemetry
git checkout -b fix/sonar-ema-cold-start
git checkout -b docs/update-protocol-table
```

### 3. Keep Your Branch Up to Date

```bash
git fetch upstream
git rebase upstream/main
```

---

## Development Environment

### Arduino / Embedded

- **Arduino IDE 2.x** (2.3.0 or later recommended)
- **Board packages:**
  - Arduino AVR Boards (for Mega and Uno)
  - ESP32 by Espressif (3.x or later)
- **Required libraries** (install via Library Manager):
  - `Wire`
  - `SoftwareSerial`
  - `Servo`
  - `EEPROM`
  - `ESP32 AsyncWebServer` (ESP32 only)
  - `ESPAsyncWebServer` + `AsyncTCP` (ESP32 only)
  - `arduinoWebSockets` (ESP32 only)
  - `mbedTLS` (bundled with ESP32 core — for AES-128-CBC)
  - `TinyGPS++` (GPS parsing)

### Python GCS

- **Python 3.8 or later**
- Install dependencies:

  ```bash
  pip install -r GCS/requirements.txt
  ```

- Key runtime dependencies: `pyserial`, `tkinter` (usually bundled), `pytest` (for testing)

### Recommended IDE

VS Code with the following extensions: C/C++ (Microsoft), Arduino, Python, Pylance.

---

## Code Style

### Arduino / C++

- **Indentation:** 2 spaces. No tabs.
- **Variable names:** `snake_case` for all variables and function parameters.
  - Example: `int motor_front_left = 0;`
- **Constants and macros:** `UPPER_CASE`.
  - Example: `#define ESC_MIN 1100`
- **Function names:** `camelCase`.
  - Example: `void updatePIDLoop()`
- **No dynamic memory allocation in ISRs or tight loops.** Do not call `malloc`, `new`, `String`
  constructors, or `Serial.print` inside interrupt service routines or any loop that executes at
  loop-rate (250 Hz). Use fixed-size buffers (`char buf[256]`) pre-allocated at startup.
- **Comments:** Every non-obvious block must have a one-line comment. Magic numbers must be named
  constants with a comment explaining the value.
- **Include guards:** All header files must use `#pragma once`.

### Python (GCS)

- **Style:** PEP-8. Use `black` or `autopep8` to auto-format before committing.
- **Type hints:** Strongly encouraged for all function signatures. Required for any new function
  added to a module with existing type hints.
- **Thread safety:** Every variable shared between threads must be protected by a `threading.Lock`.
  Document the lock's scope at its declaration site.
- **Tkinter threading rule:** Never update a Tkinter widget directly from a non-main thread.
  Schedule all GUI updates with `root.after(delay_ms, callback)`. Violations cause intermittent
  crashes that are very hard to debug.
- **Logging:** Use the `logging` module. Do not use bare `print()` in production paths; reserve it
  for CLI scripts and test output.
- **No bare `except`:** Always catch specific exception types. At minimum, catch `Exception` and log
  the traceback.

---

## Testing Requirements

### FC Logic Changes (Mega / Uno Sketches)

- Any change to PID constants, flight mode transitions, arming logic, DMS handling, or motor mixing
  **must** have a corresponding unit test added to or updated in the Python test suite
  (`tests/fc_logic/`).
- The Python test suite simulates FC state transitions via the same serial packet protocol the GCS
  uses, so hardware is not required to run these tests.
- Bench test with propellers **physically removed** is mandatory before opening a PR that touches any
  sketch.

### Python GCS Changes

- All Python changes must pass the full test suite:

  ```bash
  pytest tests/
  ```

- New features must include at least one test covering the happy path and one covering the primary
  error path.
- Aim for >80% branch coverage on new code. Use `pytest --cov` to check.

### New Commands / Protocol Changes

- Any new serial command or change to an existing command **must**:
  1. Be documented in `Docs/PROTOCOL.md` (command byte, arguments, response, notes).
  2. Update the command table in the project report source (`gen_report.py` / the LaTeX/Word source).
  3. Include a test that sends the command and asserts the expected FC response.

---

## Safety Rules for Contributors

These rules are non-negotiable. A pull request that violates any of them will be closed without
merge regardless of other merits.

1. **Never remove or weaken DMS logic.** The 3-layer dead-man switch is a core safety system.
   Any PR that removes a DMS check, increases the DMS timeout, or routes around the DMS state
   machine will be rejected.

2. **Never raise `ESC_MAX` above 1950 without a hardware review.** The current limit exists to
   protect the ESCs and frame from over-current damage. If you believe a higher limit is justified,
   open an issue and discuss it before writing code. A hardware review by the maintainer is required
   before any such change can be merged.

3. **ARM interlock checks must not be bypassed without `FORCE_ARM`.** The preflight checklist
   enforces minimum safety conditions before the drone may arm. Do not add code paths that skip
   these checks. The only sanctioned bypass mechanism is the `FORCE_ARM` flag, which is itself
   guarded and logged.

4. **All motor-related changes require a bench test with propellers removed.** This includes changes
   to motor mixing, PWM output ranges, ESC calibration routines, motor test commands, and any code
   that directly or indirectly writes to an ESC output. Document the bench test result (pass/fail,
   conditions) in your PR description.

5. **Do not introduce blocking delays in the FC main loop.** The FC runs at 250 Hz. Any `delay()`,
   `while` poll, or blocking I/O in the main loop will degrade control performance and may trigger
   the DMS watchdog. Use non-blocking state machines and timestamps.

---

## Pull Request Checklist

Before marking your PR as ready for review, confirm all of the following:

- [ ] Branch is named according to the `prefix/description` convention
- [ ] Branch is rebased on the latest `upstream/main`
- [ ] `pytest tests/` passes with no failures or errors
- [ ] Code follows style guidelines (Arduino or Python, as applicable)
- [ ] All new or changed FC logic has been bench-tested (props off) — describe the test in the PR
- [ ] PROTOCOL.md updated if any command was added or changed
- [ ] CHANGELOG.md `[Unreleased]` section updated with a concise entry
- [ ] No hardcoded credentials, keys, or passwords in any committed file
- [ ] No `auth.json`, `credentials.py`, or `credentials.h` files staged
- [ ] PR description explains the *why*, not just the *what*
- [ ] Linked to the relevant issue (use `Closes #N` or `Refs #N` in the PR body)

---

## Issue Labels and Triage

| Label              | Meaning                                                          |
|--------------------|------------------------------------------------------------------|
| `bug`              | Confirmed defect in existing behavior                            |
| `enhancement`      | New feature or improvement request                               |
| `safety`           | Relates to a safety system (DMS, ARM, ESC limits, etc.)          |
| `hardware`         | Requires physical access or bench testing to resolve             |
| `firmware`         | Change to Mega FC or Uno motor-driver sketch                     |
| `gcs`              | Change to the Python or Web GCS                                  |
| `docs`             | Documentation gap or error                                       |
| `test`             | Missing or failing test coverage                                 |
| `good first issue` | Suitable for new contributors                                    |
| `[SECURITY]`       | Security vulnerability — do NOT post details publicly            |
| `wontfix`          | Acknowledged but will not be addressed                           |
| `needs-repro`      | Bug report needs a reproducible test case before triage proceeds |

New issues are triaged within 72 hours on a best-effort basis. Issues labelled `safety` are
prioritised and will receive a response within 24 hours.

---

## Reporting Security Vulnerabilities

**Do not open a public GitHub issue for a security vulnerability.**

Please follow the process described in [SECURITY.md](SECURITY.md). In short: open a **private**
GitHub issue with the label `[SECURITY]`, or use the private contact method listed there. We will
acknowledge your report within 48 hours.

---

## Questions?

If you are unsure whether a proposed change is in scope or safe to implement, open a discussion
issue before writing any code. It is far easier to course-correct a design than to review and reject
a large pull request.

Thank you for helping make SUDARSHAN safer and more capable.
