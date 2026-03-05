# HTTP over Unix Socket Migration (TL;DR + versioned endpoints)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** replace custom length-prefixed socket protocol with HTTP over the same Unix socket (`/run/tinta4plus.sock`), using explicit versioned verb endpoints.

## API contract (v1)

Use these endpoints (no generic `/command`):

- `POST /v1/eink/enable`
- `POST /v1/eink/disable`
- `POST /v1/eink/refresh`
- `POST /v1/eink/mode/dynamic`
- `POST /v1/eink/mode/reading`
- `GET  /v1/ec/status`
- `GET  /v1/frontlight`
- `POST /v1/frontlight/enable` (optional body `{"brightness_level": <int>}`)
- `POST /v1/frontlight/disable`
- `POST /v1/frontlight/brightness` (body `{"level": <int>}`)

### Example: set brightness

Request:
```http
POST /v1/frontlight/brightness HTTP/1.1
Content-Type: application/json

{"level":80}
```

Response:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":true,"readback":"0x50","level":80,"message":"Brightness set to 80"}
```

### Error behavior

- invalid JSON body: `400`
- unknown route: `404`
- wrong method: `405`
- command-level errors still return current JSON error payload shape

## Access logging requirement (server console)

Every request must log one access line through project logger (not raw stderr default), including:
- client (`unix-client`)
- method
- path
- status code
- duration in ms

Example:
```text
HTTP unix-client "POST /v1/frontlight/brightness" 200 3.8ms
```

## Keep unchanged

- Socket path (`/run/tinta4plus.sock`)
- systemd socket activation (FD 3)
- business logic in `handle_command()` (transport wrapper maps endpoint -> existing command)
- response JSON keys (`success`, `error`, plus command-specific fields)

---

## Step 0 (done): Baseline tests for old protocol

**File:** `tests/test_unix_socket_protocol.py`

Run:
```bash
uv run -m unittest tests/test_unix_socket_protocol.py
```

---

## Step 1 (RED): Add failing HTTP client endpoint tests

**Create:** `tests/test_http_unix_socket_protocol.py`

Test exactly:
1. client calls endpoint-specific paths (e.g. `POST /v1/eink/refresh`)
2. expected JSON body for parameterized routes (e.g. brightness)
3. parses JSON response
4. maps transport/HTTP failures to `RuntimeError`

Run (should fail before client refactor):
```bash
uv run -m unittest tests/test_http_unix_socket_protocol.py -v
```

---

## Step 2 (GREEN): Refactor client transport + route mapping

**Modify:** `HelperClient.py`

- replace struct framing with HTTP-over-unix-socket
- add map from current `send_command("...")` values to v1 routes/methods/body
- keep public API stable: `send_command(command, **params)`

Run:
```bash
uv run -m unittest tests/test_http_unix_socket_protocol.py -v
```

---

## Step 3 (RED): Add failing daemon endpoint + access-log tests

**Create:** `tests/test_helper_daemon_http.py`

Test exactly:
1. each v1 route maps to expected command behavior
2. invalid JSON -> 400
3. unknown route -> 404
4. wrong method -> 405
5. access log emitted with method/path/status/duration

Run (should fail before daemon refactor):
```bash
uv run -m unittest tests/test_helper_daemon_http.py -v
```

---

## Step 4 (GREEN): Refactor daemon transport + endpoint router

**Modify:** `HelperDaemon.py`

- replace manual recv/send loop with HTTP handler over FD 3
- endpoint router maps v1 route+method to existing command dispatcher
- implement custom access logging to existing logger

Run:
```bash
uv run -m unittest tests/test_helper_daemon_http.py -v
```

---

## Step 5: Full regression + docs

**Modify:** `README.md`

- document v1 endpoint table
- include one request/response example
- note access log format

Run all tests:
```bash
uv run -m unittest
```

Sanity commands (via existing UI/CLI):
- eink: enable/disable/refresh/mode
- EC/frontlight: status/state/enable/disable/brightness
