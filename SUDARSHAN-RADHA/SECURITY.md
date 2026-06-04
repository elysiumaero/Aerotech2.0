# Security Policy — SUDARSHAN UAV

## Supported Versions

| Version | Supported | Notes |
|---------|-----------|-------|
| 1.2.x   | ✅ Yes     | Current release — security patches applied |
| 1.1.x   | ❌ No      | Upgrade to 1.2 — contains critical DMS race fix |
| 1.0.x   | ❌ No      | Upgrade to 1.2 — multiple safety-critical issues |

## Scope

The following are considered security vulnerabilities in this project:

### In-scope
- **Unauthorized flight commands** — sending ARM/KILL/OVERRIDE without authentication
- **DMS bypass** — any technique that prevents the dead-man switch from firing
- **Authentication bypass** — bypassing the GCS login, priority lock, or web GCS auth
- **Motor command injection** — injecting arbitrary motor throttle values via UART or TCP
- **Credential exposure** — AES keys, passwords, or auth hashes leaking into logs, telemetry, or git history
- **Replay attacks** — replaying a captured ARM or KILL command
- **Denial-of-service on FC** — flooding UART or TCP in a way that locks up the Mega and disables the DMS
- **Encryption downgrade** — forcing plaintext transmission on an encrypted link

### Out of scope
- Physical access attacks (attacker has physical control of the drone)
- RF jamming or signal interference (hardware/regulatory problem)
- Prop strikes and mechanical damage
- GPS spoofing (no GPS module on FC)
- Social engineering

## Threat Model

| Assumption | Detail |
|---|---|
| WiFi AP is trusted | SUDARSHAN_AP is assumed to be on a private local network without untrusted clients. There is no TLS on the HTTP web GCS (port 80) by design — acceptable when no external clients can join the AP. |
| Physical security of drone | The Mega→Uno UART motor packets use XOR checksum only (no HMAC). An attacker with physical wire access could inject motor commands. Accepted risk — physical security of the hardware is assumed. |
| Credentials not in git | `auth.json`, `credentials.py`, and `credentials.h` are gitignored and must never be committed. |
| AES encryption optional | AES-128-CBC on the TCP GCS link is opt-in. It should be enabled for any deployment outside a private bench environment. |

## Security Architecture

```
[Phone browser] ──HTTP (no TLS)──► [ESP32 :80/:81]
[Laptop GCS]    ──TCP (AES opt.)──► [ESP32 :5760]
                                         │
                                    ┌────▼─────┐
                                    │ Command  │
                                    │Whitelist │  ← rejects unknown commands
                                    │Rate Limit│  ← 150ms min between web cmds
                                    └────┬─────┘
                                         │ UART (no encryption — local bus)
                                    ┌────▼─────┐
                                    │  Mega FC │
                                    │Whitelist │  ← unknown cmds logged + rejected
                                    │Rate Limit│  ← MOTOR_TEST 5s, CAL_ESC 10s
                                    │Slew Limit│  ← OVERRIDE throttle max 50µs/cmd
                                    └──────────┘
```

**Priority lock:** When the Python laptop GCS is connected on TCP :5760, all web GCS commands are blocked. Override codes: `1410` (session) or `980752` (master — all auth checks). The master code is stored in firmware only and must be changed before production deployment.

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available could allow an attacker to exploit the vulnerability during a flight.

### Steps to report:

1. Open a **private** GitHub issue on this repository with the title prefix `[SECURITY]`
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact (can it cause loss of control? inject commands? disable DMS?)
   - Any proof-of-concept (do not include live exploit code)
3. Label the issue `security` and `private`

### Response SLA:

| Severity | Acknowledgement | Patch |
|---|---|---|
| CRITICAL (loss of control, DMS bypass) | Within 24 hours | Within 7 days |
| HIGH (auth bypass, command injection) | Within 48 hours | Within 14 days |
| MEDIUM/LOW | Within 7 days | Within 30 days |

We will coordinate disclosure timing with you. A CVE will not be filed for this project (not a commercial product), but the fix will be documented in CHANGELOG.md with a `[SECURITY]` tag.

## Known Security Limitations

These are known limitations accepted by design — they are **not** reportable vulnerabilities:

1. **No HMAC on motor packets** — The Mega→Uno 10-byte binary packet uses XOR checksum only. Physical wire access can inject motor commands. Mitigation: physical security of drone.

2. **Web GCS served over HTTP** — Port 80 has no TLS. Acceptable on a private AP with no untrusted clients. Do not deploy in a public WiFi environment.

3. **Hardcoded override codes in ESP32 firmware** — `PRIORITY_PASS="1410"` and `MASTER_PASS="980752"` are in firmware. Physical flash access exposes them. Change these values before any deployment.

4. **No command signing** — TCP commands are not signed (only optionally encrypted). On an unencrypted link, a MITM on the same WiFi AP can inject commands. Mitigation: enable AES encryption.

5. **Single-factor authentication** — GCS login uses SHA-256 hashed passwords stored locally. No 2FA. Acceptable for a research project with a single operator.

## Security Changelog

| Version | Change |
|---|---|
| 1.2.0 | AES malloc failures no longer silently transmit plaintext |
| 1.2.0 | ESP32: rate limit on /api/cmd (150ms min between commands) |
| 1.2.0 | ESP32: command whitelist — unknown commands dropped before reaching FC UART |
| 1.2.0 | FC: unknown commands logged and rejected (no longer silently ignored) |
| 1.2.0 | FC: FORCE_ARM requires explicit `"confirm":"FORCE_ARM"` field |
| 1.2.0 | FC: MOTOR_TEST rate-limited to once per 5s; CAL_ESC to once per 10s |
| 1.2.0 | FC: OVERRIDE throttle slew rate capped at 50µs per command |
| 1.2.0 | Python GCS: outgoing commands sanitised (numeric fields clamped to safe ranges) |
| 1.2.0 | Python GCS: armed/mode state protected by threading.RLock |
