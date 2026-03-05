# HTTP over Unix Socket Migration (TL;DR)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** switch helper protocol from custom length-prefix JSON to HTTP, on the same Unix socket (`/run/tinta4plus.sock`).

**Keep unchanged:**
- Socket path
- systemd socket activation (FD 3)
- command payload shape: `{ "command": "...", "params": {...} }`
- response JSON keys (`success`, `error`, command-specific fields)

---

## Step 0 (done): Baseline tests for current protocol

**File:** `tests/test_unix_socket_protocol.py`

Covers:
- client sends length-prefixed JSON
- daemon sends length-prefixed JSON
- daemon handles one full request/response command roundtrip

Run:
```bash
uv run -m unittest tests/test_unix_socket_protocol.py
```

---

## Step 1: Add failing HTTP client tests (RED)

**Create:** `tests/test_http_unix_socket_protocol.py`

Test expectations:
- client sends `POST /command`
- `Content-Type: application/json`
- body `{command, params}`
- parses JSON response

Run (should fail before client refactor):
```bash
uv run -m unittest tests/test_http_unix_socket_protocol.py -v
```

---

## Step 2: Refactor client transport (GREEN)

**Modify:** `HelperClient.py`

- replace struct framing with HTTP-over-unix-socket connection
- keep `send_command(command, **params)` API stable
- map HTTP/socket errors to current `RuntimeError` pattern

Run:
```bash
uv run -m unittest tests/test_http_unix_socket_protocol.py -v
```

---

## Step 3: Add failing HTTP daemon tests (RED)

**Create:** `tests/test_helper_daemon_http.py`

Test expectations:
- accepts `POST /command`
- returns JSON response
- invalid JSON => HTTP 400 + `{success:false,error:...}`
- unknown route => HTTP 404

Run (should fail before daemon refactor):
```bash
uv run -m unittest tests/test_helper_daemon_http.py -v
```

---

## Step 4: Refactor daemon transport (GREEN)

**Modify:** `HelperDaemon.py`

- keep `handle_command()` unchanged
- replace manual recv/send framing with HTTP request handler
- serve over systemd FD 3 Unix socket

Run:
```bash
uv run -m unittest tests/test_helper_daemon_http.py -v
```

---

## Step 5: Final regression + docs

**Modify:** `README.md` (helper protocol section)

Run all tests:
```bash
uv run -m unittest
```

Sanity check commands still work:
- `enable-eink`, `disable-eink`, `refresh-eink`
- `set-dynamic`, `set-reading`
- `get-ec-status`, `get-frontlight-state`
- `enable-frontlight`, `disable-frontlight`, `set-brightness`

---

## Commit plan for now

Commit only baseline tests + TL;DR plan:
```bash
git add tests/test_unix_socket_protocol.py docs/plans/2026-03-05-http-over-unix-socket-migration.md
git commit -m "test(protocol): add unix-socket baseline tests and migration plan"
```
