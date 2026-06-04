# Concurrency & Shared-State Audit — SUDARSHAN UAV

**Audit date:** 2026-06-04  
**Scope:** All four firmware/software components  
**Auditor:** Senior Engineering Review (Claude Code)

---

## Executive Summary

| Component | Threading Model | Real Races | Logical Races | Fixed in v1.2 |
|---|---|---|---|---|
| Python GCS | Multi-threaded (recv_loop + Tk main) | 6 | 2 | 4 |
| ESP32 | Single-threaded Arduino loop | 0 | 4 | 2 |
| Mega FC | Single-threaded Arduino loop | 0 | 4 | 1 |
| Uno Motor Driver | Single-threaded | 0 | 0 | 1 |

---

## 1. Python GCS (`radha_gcs.py`)

The Python GCS has **two real threads**: `recv_loop` (background socket reader) and the main Tkinter event loop. Any shared variable written in one and read in the other without a lock is a data race.

### 1.1 — `self._armed` / `self._mode` [FIXED in v1.2]
- **Written:** `_apply_telem()` → called via `root.after(0, ...)` from recv_loop
- **Read:** `_send_cmd()`, `_set_alt()`, `_exec_preset()`, button callbacks
- **Fix applied:** `threading.RLock()` wraps all reads/writes

### 1.2 — `self._last_seq` [FIXED in v1.2]
- **Written & Read:** `_on_telem()` in recv_loop
- **Fix applied:** `threading.Lock()` + reboot-aware gap detection

### 1.3 — `PreflightRunner._ack_result` [FIXED in v1.2]
- **Written:** `notify_ack()` in recv_loop
- **Read:** `_run_test()` in a preflight thread
- **Fix applied:** `queue.Queue(maxsize=1)` replaces shared variable

### 1.4 — `FlightLog` file write [OPEN — MEDIUM]
- **Issue:** `FlightLog.log()` writes to a file. It is called from `recv_loop` thread (telemetry logging) AND from the main thread (command logging). Python's GIL makes individual `file.write()` calls atomic, but multi-line writes (timestamp + data as two separate calls) can interleave.
- **Fix:** Wrap `FlightLog.log()` body with `threading.Lock()`.
- **Severity:** MEDIUM — log file corruption only; no flight impact.

### 1.5 — `ConnectionManager.close()` vs `recv_loop` [OPEN — HIGH]
- **Issue:** `close()` is called from the main thread (disconnect button, shutdown). It sets `self._sock = None` and calls `sock.close()`. The `recv_loop` thread is simultaneously blocking on `sock.recv()`. The sequence:
  1. Main: `self._sock = None` (assignment)
  2. recv_loop: `self._sock.recv()` → AttributeError because `_sock` is now None, OR OSError because socket is closed mid-recv
  The exception is caught by the recv_loop try/except, which causes it to exit cleanly — so this does not crash the app, but it means the recv_loop can get one spurious exception on every disconnect.
- **Fix:** Set a `self._stopping` flag before closing the socket. Check the flag in the except clause to distinguish intentional close from real errors.
- **Severity:** HIGH for correctness; LOW for safety (drone not affected).

### 1.6 — `self._conn_ok` flag [OPEN — MEDIUM]
- **Issue:** `self._conn_ok` is set in `recv_loop` (on connect/disconnect) and read in the main thread for UI state. No lock.
- **Fix:** Protect with `_state_lock` alongside `_armed`/`_mode`.
- **Severity:** MEDIUM — worst case: UI shows connected when disconnected or vice versa for one Tk update cycle.

### 1.7 — Tkinter widget updates from recv_loop [OPEN — HIGH]
- **Issue:** Some widget updates (`label.config(text=...)`, `canvas.delete(...)`) may be called directly in `_apply_telem()`. Tkinter is **not thread-safe** — widget updates must happen on the main thread. While most are marshalled via `root.after(0, ...)`, any direct widget call in a function that might be reached from recv_loop is a race.
- **Affected:** Status bar updates, telemetry label updates, LED indicators.
- **Fix:** Audit every widget update path. All updates reachable from recv_loop must go through `root.after(0, callback)`.
- **Severity:** HIGH — Tkinter crashes with obscure segfaults or hangs under this condition.

### 1.8 — DMS timer thread [OPEN — LOW]
- **Issue:** The DMS timer is a `threading.Timer` that calls `send({"cmd":"HOVER"})`. The `send()` method also called from the main thread. Python's GIL ensures the `json.dumps()` + `sock.sendall()` sequence doesn't interleave, but the timer resetting logic (`self._dms.cancel()` + new timer) has a small window where two HOVER commands could be queued.
- **Fix:** Wrap timer cancel/restart in `threading.Lock()`.
- **Severity:** LOW — sends an extra HOVER at worst.

---

## 2. ESP32 (`ATLAS_ESP32_Bridge_v2.ino`)

The ESP32 Arduino runs a **single cooperative loop**. There is no preemption between `readFC()`, `readGCS()`, `httpServer.handleClient()`, and `wsServer.loop()`. However, HTTP handler callbacks run inline during `httpServer.handleClient()`, which can be called between any two `readFC()` byte reads. This creates logical ordering races.

### 2.1 — `gps` struct partial read during NMEA multi-line parse [OPEN — MEDIUM]
- **Issue:** The GPS struct is updated field-by-field across multiple NMEA sentences ($GPGGA for lat/lon/fix/sats, $GPRMC for heading). The sequence in `loop()`:
  ```
  readPhone() → parses one NMEA line → updates gps.lat
  httpServer.handleClient() → handleWebTelem() → reads gps.lat AND gps.lon
  readPhone() → parses next line → updates gps.lon
  ```
  A telemetry poll between two NMEA lines can return `lat` from sentence N+1 but `lon` from sentence N.
- **Fix:** Use a double-buffer: accumulate into `gps_pending`, then atomically copy to `gps` when a complete fix is assembled (after both GPGGA and GPRMC are parsed).
- **Severity:** MEDIUM — GPS display shows stale/mismatched coordinates for one poll cycle.

### 2.2 — `lastTelemJson` / `lastAckJson` read while being built [LOW — already mitigated]
- **Issue:** `bufFC` is built byte-by-byte in `readFC()`. `lastTelemJson` is only assigned when `\n` is found: `lastTelemJson = bufFC`. So the assignment is to a complete line. HTTP handlers that read `lastTelemJson` will either read the previous complete line or the new one — both valid. Single-threaded assignment is atomic.
- **Status:** Safe as-is.

### 2.3 — `webGcsLocked` one-cycle lag [OPEN — LOW]
- **Issue:** In `loop()`, if `httpServer.handleClient()` runs BEFORE `acceptClients()`, a new TCP connection that just arrived causes `webGcsLocked` to be set AFTER the web command is processed in the same loop iteration. The web command for that single cycle is not blocked.
- **Fix:** Call `acceptClients()` before `httpServer.handleClient()` in `loop()`.
- **Severity:** LOW — one command can slip through on the exact loop iteration of TCP connection.

### 2.4 — `gcsPrevConn` edge detection missed event [OPEN — LOW]
- **Issue:** If a GCS disconnects and a new one connects within the same `loop()` iteration (extremely unlikely — requires sub-millisecond TCP churn), `gcsPrevConn` would see `true → true` and miss the disconnect → `webGcsLocked` would not be reset.
- **Fix:** Compare against client socket ID, not just `connected()` boolean.
- **Severity:** LOW — requires sub-ms TCP reconnect to trigger.

---

## 3. Mega FC (`SUDARSHAN_FC.ino`)

The Mega runs a **single-threaded Arduino loop**. No true concurrency. However, blocking `delay()` calls inside command handlers create extended dead zones where no loop code runs — equivalent to a thread stall.

### 3.1 — CRITICAL: UART FIFO overflow during `escsArm()` [OPEN — HIGH]
- **Issue:** `escsArm()` calls `delay(2500)`. This 2.5-second blocking call is inside `handleCmd()`, which is called from `readUART()` in `loop()`. During the delay:
  - The Mega's hardware UART FIFO (64 bytes) fills in ~5 ms at 115200 baud
  - Hundreds of bytes from ESP32 (telemetry ACKs, GPS updates) are lost
  - After `delay()` returns, `readUART()` continues with whatever bytes survived in the FIFO, potentially mid-packet
  - At minimum: the GCS receives no ACK for ~2.5s after ARM; DMS timers on both ESP32 and FC may fire if commands pile up
- **Severity:** HIGH — UART corruption during arming. FC DMS is safe because `lastCmdMs` is set before the delay.
- **Fix:** During the arming delay, drain the UART periodically:
  ```cpp
  void escsArm() {
    escsKill();
    // Hold 1000µs for 2.5s — drain UART every 50ms to prevent FIFO overflow
    unsigned long t0 = millis();
    while (millis() - t0 < 2500) {
      while (ESP_SERIAL.available()) ESP_SERIAL.read();  // drain, don't process
      delay(50);
    }
  }
  ```

### 3.2 — UART FIFO overflow during MOTOR_TEST / SPIN_CH / CAL_ESC [OPEN — HIGH]
- **Issue:** Same problem as 3.1. `MOTOR_TEST` has `delay(dur)` up to 2000ms. `SPIN_CH` has `delay(dur)` up to 3000ms. `CAL_ESC` has two `delay(3000)` calls = **6 seconds total** of UART blindness.
- **Fix:** Same pattern — drain ESP_SERIAL during blocking delays.
- **Severity:** HIGH for CAL_ESC (6s), HIGH for SPIN_CH (3s), MEDIUM for MOTOR_TEST (2s). All are DISARMED-only operations, so flight is not affected, but GCS loses sync.

### 3.3 — `landCount` not reset on non-LAND mode transitions [OPEN — MEDIUM]
- **Issue:** `landCount` (global, line 159) is incremented in MODE_LAND and reset when `alt_cm >= 8.0f`. If the drone enters LAND, bounces above 8cm (resetting landCount to 0), then GCS sends HOVER — mode changes to HOVER. If LAND is commanded again immediately, `landCount` starts from 0 (correct). But if the drone somehow triggers LAND mid-flight with `alt_cm < 8.0f` for 6 consecutive readings before the ESC arming check, a false landing detect could fire.
- **Fix:** Reset `landCount = 0` in the LAND command handler (already done) and also reset it on any mode transition OUT of LAND.
- **Severity:** MEDIUM — false early disarm possible in edge case.

### 3.4 — `lastDrop` static local persists across LAND invocations [OPEN — LOW]
- **Issue:** In `controlLoop()`, the LAND/FAILSAFE case has `static unsigned long lastDrop = 0`. On second LAND invocation, `lastDrop` still holds the timestamp of the last descent step from the previous LAND. If the previous LAND completed recently, the new LAND might skip the first descent step (up to 83ms delay).
- **Fix:** Reset `lastDrop = 0` (or `lastDrop = millis() - 100`) when transitioning into MODE_LAND.
- **Severity:** LOW — maximum 83ms delay on first descent step of re-LAND.

---

## 4. Uno Motor Driver (`SUDARSHAN_MOTOR_UNO.ino`)

### 4.1 — Packet timeout self-recovery [FIXED in v1.2]
- `idx` reset to 0 after 10ms without a byte — self-recovering UART desync.

### 4.2 — No remaining concurrency issues
- Single-threaded, no shared state, no delay() calls during packet processing.

---

## Summary: Remaining Open Issues

| ID | Component | Function | Issue | Severity | Fix |
|----|-----------|----------|-------|----------|-----|
| C1 | Python GCS | FlightLog.log() | No lock on file write from 2 threads | MEDIUM | Add threading.Lock() |
| C2 | Python GCS | ConnectionManager.close() | Socket close races recv_loop.recv() | HIGH | Add _stopping flag |
| C3 | Python GCS | _apply_telem() | Direct widget updates from non-main thread | HIGH | Audit, use root.after() |
| C4 | Python GCS | _conn_ok | Unprotected across threads | MEDIUM | Add to _state_lock |
| C5 | Python GCS | DMS timer | Timer cancel/restart race | LOW | Add threading.Lock() |
| C6 | ESP32 | readPhone() + handleWebTelem() | GPS struct partial read between NMEA lines | MEDIUM | Double-buffer gps struct |
| C7 | ESP32 | loop() ordering | webGcsLocked set after http handler in same cycle | LOW | Call acceptClients() first |
| C8 | FC | escsArm() | UART FIFO overflow during 2.5s delay | HIGH | Drain UART during delay |
| C9 | FC | CAL_ESC / MOTOR_TEST / SPIN_CH | UART FIFO overflow during blocking delays (up to 6s) | HIGH | Drain UART during delay |
| C10 | FC | MODE_LAND logic | landCount not reset on transition out of LAND | MEDIUM | Reset on mode change |
| C11 | FC | controlLoop static lastDrop | Stale timestamp on second LAND invocation | LOW | Reset on mode entry |

---

## Recommended Fix Order

1. **C8 + C9** (FC UART overflow during blocking delays) — highest real impact; GCS loses sync for seconds
2. **C2 + C3** (Python socket close race + widget thread safety) — causes intermittent crashes in long sessions
3. **C1 + C4** (Python log lock + conn_ok lock) — data consistency
4. **C6** (ESP32 GPS double-buffer) — GPS display correctness
5. **C10** (landCount reset) — edge-case flight safety
6. **C7 + C11** (minor ordering issues) — low priority
