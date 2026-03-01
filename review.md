# Branch Review (`pr-1..HEAD`)

## Scope
Reviewed all 13 commits from `pr-1` to `HEAD` on `taras/fixes`.

## Summary
Overall direction is good. Migrating from ad-hoc `pkexec` helper startup to systemd socket activation improves reliability and security posture.

---

## Findings

### 1) High — installer can run with empty `--user`
**File:** `scripts/install-systemd-helper-root.sh`

`USER_NAME` defaults to empty, but install mode always runs:

```bash
usermod -a -G tinta4plus "$USER_NAME"
```

If `--user` is omitted/empty, install fails unpredictably.

**Recommendation:**
Fail early in install mode when `--user` is empty, with a clear error message.

---

### 2) Medium — stale PID file possible on early startup failure
**File:** `HelperDaemon.py`

`run()` creates PID file before `_create_socket()`. If `_create_socket()` fails (e.g., missing `LISTEN_FDS`/`LISTEN_PID`), `finally: shutdown()` is called, but `shutdown()` returns immediately when `self.running` is `False`, leaving PID file behind.

**Recommendation:**
Use a trap-like cleanup approach in Python: make `shutdown()` idempotent and always perform cleanup (PID/socket removal, watchdog cancel, hardware cleanup) even when `self.running` was never set to `True`. Optionally also register cleanup with `atexit` for extra safety.

---

### 3) Low — outdated comment
**File:** `Tinta4Plus.py` (`on_closing`)

Comment says disconnect “sends shutdown command”, but shutdown command behavior was intentionally removed.

**Recommendation:**
Update comment to reflect current behavior.

---

### 4) Low — desktop launcher tied to checkout path
**File:** `scripts/install-systemd-helper-root.sh`

Desktop file uses:
- `Exec=$APP_MAIN`
- `Path=$SOURCE_DIR`

This ties launcher validity to the original source directory.

**Recommendation:**
Use a stable launcher/entrypoint and reference it from the `.desktop` file. In Python, resolve paths relative to the script file (the `$0` equivalent) using `Path(__file__).resolve().parent` (or `os.path.dirname(os.path.abspath(__file__))`) so runtime behavior does not depend on the current working directory.

---

## Positive notes

- Socket migrated to `/run/tinta4plus.sock` with `0660` and `SocketGroup=tinta4plus`.
- Client no longer tries to shut down daemon directly (correct for socket activation).
- Added installer drift detection via `--check`.
- GUI install/upgrade flow and group-membership handling are sensible.
- Python changed files compile cleanly.
