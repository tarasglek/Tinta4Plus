# Remove Blind Sleeps with Readiness Polls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate fixed `time.sleep(...)` calls from production code and replace them with bounded, observable readiness polling so display switching converges as fast as the system is actually ready while preserving reliability.

**Architecture:** Introduce small monotonic-time polling helpers around concrete system predicates instead of fixed delays. Keep RandR readiness checks centralized in `DisplayManager`, keep mode-switch hardware readiness checks in `mode_switch.py`, and replace GUI helper reconnect sleeps with socket reconnect polling. Poll loops must have explicit timeouts, short intervals, structured logging, and fail with the same or better safety semantics as today.

**Tech Stack:** Python 3, X11/XRandR (`xrandr`), existing helper HTTP API, `subprocess`, `time.monotonic`, `unittest` / `unittest.mock`

---

## Sleep inventory to remove

Current production-code sleeps to eliminate:

- `mode_switch.py`
  - `switch_to_eink()`: `time.sleep(0.5)` after helper E-Ink/frontlight prep
  - `switch_to_oled()`: `time.sleep(0.5)` after privacy image launch
  - `switch_to_oled()`: `time.sleep(2.0)` after disable-eink/disable-frontlight prep
- `DisplayManager.py`
  - `enable_display()`: `time.sleep(self.XRANDR_APPLY_DELAY)`
  - `finalize_single_display()`: three `time.sleep(self.XRANDR_APPLY_DELAY)` sites
  - `disable_display()`: `time.sleep(self.XRANDR_APPLY_DELAY)`
  - `display_fullscreen_image()`: `time.sleep(self.IMAGE_DISPLAY_DELAY)` in both `feh` and `imv` branches
- `Tinta4Plus.py`
  - `attempt_helper_restart()`: `time.sleep(0.5)` before reconnect attempt

The finished diff should remove all of the above from production code.

---

## Task 1: Add failing tests that describe poll-based behavior instead of fixed waits

**Files:**
- Modify: `tests/test_display_manager_rotation.py`
- Modify: `tests/test_mode_switch_rotation.py`
- Modify: `tests/test_tinta4plus_ui_state.py`
- Verify: `DisplayManager.py`
- Verify: `mode_switch.py`
- Verify: `Tinta4Plus.py`

### Step 1: Add failing tests for RandR polling in `DisplayManager`

Add tests proving the display methods do not depend on a single blind sleep and instead keep checking until the target predicate becomes true.

Coverage to add:
- `enable_display()` polls `is_display_active(display_name)` until it becomes true, then returns success.
- `enable_display()` returns false after timeout if `is_display_active(display_name)` never becomes true.
- `disable_display()` polls until `is_display_active(display_name)` becomes false.
- `finalize_single_display()` polls `_verify_display_target_state(...)` until it succeeds.
- the retry path in `finalize_single_display()` also uses polling after the baseline reset and reapply.

Use `side_effect` sequences like `[False, False, True]` to prove repeated checks happen.

### Step 2: Add failing tests for mode-switch prep polling

Add tests proving:
- `switch_to_eink()` waits on a helper readiness predicate instead of calling `time.sleep(0.5)`.
- `switch_to_oled()` waits on a helper readiness predicate instead of calling `time.sleep(2.0)`.
- `switch_to_oled()` waits for privacy image readiness via a polling helper instead of `time.sleep(0.5)`.
- no production path in `mode_switch.py` calls `time.sleep(...)` during a successful switch.

The tests should mock dedicated helper functions you will add, not raw `time.sleep`.

### Step 3: Add failing tests for GUI reconnect polling

Add tests proving:
- `attempt_helper_restart()` retries connection until it succeeds or times out.
- it no longer depends on a single fixed `time.sleep(0.5)` before reconnect.
- on success, it still triggers `_reconcile_from_live_state()` and schedules the UI follow-up exactly as before.

### Step 4: Run the focused tests and confirm expected failures

Run:
```bash
python3 -m unittest -v \
  tests.test_display_manager_rotation \
  tests.test_mode_switch_rotation \
  tests.test_tinta4plus_ui_state
```

Expected:
- FAIL because the new poll helpers and retry orchestration do not exist yet.

### Step 5: Commit the red tests

```bash
git add tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_tinta4plus_ui_state.py
git commit -m "test(display): specify readiness polling behavior"
```

---

## Task 2: Add one bounded polling primitive and use it for RandR state convergence

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

### Step 1: Add a generic polling helper to `DisplayManager`

Add a helper such as:
```python
def _poll_until(self, predicate, *, timeout_s, interval_s, description):
    deadline = time.monotonic() + timeout_s
    last_value = None
    while time.monotonic() < deadline:
        last_value = predicate()
        if last_value:
            return True
    return False
```

Implementation requirements:
- use `time.monotonic()`
- small poll interval constant, e.g. `0.05` or `0.1`
- explicit timeout constants for:
  - output active/inactive convergence
  - compact final-state verification
  - image viewer readiness
- log start / success / timeout with the `description`
- do **not** call `time.sleep`; use a non-blocking wait strategy only inside the poll helper if needed via `select`, `Event.wait`, or short monotonic pacing logic. If you choose to pace with a tiny wait primitive, keep it isolated in one helper and remove all direct production sleeps elsewhere.

### Step 2: Convert `enable_display()` to poll on actual display activation

Replace `time.sleep(self.XRANDR_APPLY_DELAY)` with polling for:
- `self.is_display_active(display_name)`

Success condition:
- returns true as soon as the display is active

Failure condition:
- logs timeout and returns false

### Step 3: Convert `disable_display()` to poll on actual display deactivation

Replace `time.sleep(self.XRANDR_APPLY_DELAY)` with polling for:
- `not self.is_display_active(display_name)`

### Step 4: Convert `finalize_single_display()` to poll on target-state verification

Replace each post-apply sleep with polling for:
- `self._verify_display_target_state(display_name, target_state)`

Retry behavior requirements:
- first apply polls for verified final state
- on failure, reset baseline once
- poll for baseline activation only if needed for correctness
- reapply target state once
- poll again for verified final state
- no unbounded loops

### Step 5: Remove stale delay constants if they are no longer needed

Delete or rename:
- `XRANDR_APPLY_DELAY`

Replace with timeout/interval constants such as:
- `XRANDR_POLL_INTERVAL`
- `XRANDR_ACTIVATION_TIMEOUT`
- `XRANDR_FINALIZE_TIMEOUT`

### Step 6: Run focused tests

Run:
```bash
python3 -m unittest -v tests.test_display_manager_rotation
```

Expected:
- PASS for the new polling tests
- existing display-manager tests stay green

### Step 7: Commit

```bash
git add DisplayManager.py tests/test_display_manager_rotation.py
git commit -m "refactor(display): poll for RandR convergence"
```

---

## Task 3: Replace mode-switch prep sleeps with helper/device readiness polling

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`
- Verify: helper client API already used by `helper_command(...)`

### Step 1: Define the observable predicates for prep readiness

Add small mode-switch helpers such as:
- `_wait_for_eink_enabled(helper, logger, timeout_s=...)`
- `_wait_for_eink_disabled(helper, logger, timeout_s=...)`
- `_wait_for_frontlight_state(helper, logger, enabled, timeout_s=...)`
- `_wait_for_privacy_image_ready(display_mgr, logger, image_process, timeout_s=...)`

Use observable state only. Preferred predicates:
- helper state endpoint / frontlight endpoint if already available through the helper client
- process liveness plus X11 window detection for privacy image if available
- bounded timeout with useful warning logs on failure

Do **not** add another hardcoded dwell time.

### Step 2: Replace E-Ink prep sleep with readiness polling

In `switch_to_eink()`:
- keep `enable-eink`
- keep optional `enable-frontlight`
- replace `time.sleep(0.5)` with one bounded wait that confirms the E-Ink path is ready for display convergence

Recommended predicate order:
- confirm helper reports E-Ink enabled
- if frontlight requested, confirm frontlight enabled / brightness applied

### Step 3: Replace OLED prep sleep with readiness polling

In `switch_to_oled()`:
- after `disable-eink`, poll until helper reports E-Ink disabled
- after `disable-frontlight`, poll until helper reports frontlight disabled
- remove `time.sleep(2.0)` entirely

### Step 4: Replace privacy-image launch sleep with readiness polling

Update the privacy-image path so `display_fullscreen_image()` or a new companion helper returns enough information to wait for readiness without a fixed sleep.

Recommended approach:
- poll for `image_process.poll() is None`
- if running under X11 and a tool-free predicate is available, also poll for a mapped client window owned by that PID
- if no stronger signal is available, treat a still-running process after a short bounded poll as ready and document the limitation in code comments

### Step 5: Run focused mode-switch tests

Run:
```bash
python3 -m unittest -v tests.test_mode_switch_rotation tests.test_mode_switch_state
```

Expected:
- PASS
- no direct production `time.sleep(...)` remains in `mode_switch.py`

### Step 6: Commit

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py
git commit -m "refactor(mode-switch): replace prep sleeps with readiness polls"
```

---

## Task 4: Remove image-viewer sleeps from `DisplayManager.display_fullscreen_image()`

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`
- Verify: callers in `mode_switch.py`

### Step 1: Add failing or expanded tests for image-launch readiness

Add tests proving:
- `display_fullscreen_image()` no longer sleeps after `Popen`
- it returns a process object immediately when launch succeeds
- a separate readiness helper performs any bounded readiness polling

### Step 2: Refactor image display API

Refactor toward one of these patterns:

Preferred:
```python
process = display_fullscreen_image(...)
wait_for_fullscreen_image(process, ...)
```

Alternative:
```python
process, ready_checker = display_fullscreen_image(...)
```

Keep responsibilities clear:
- launch function launches only
- wait function verifies readiness only

### Step 3: Remove `IMAGE_DISPLAY_DELAY`

Delete:
- `IMAGE_DISPLAY_DELAY`

Replace with:
- `IMAGE_READY_TIMEOUT`
- `IMAGE_READY_POLL_INTERVAL`

### Step 4: Run focused tests

Run:
```bash
python3 -m unittest -v tests.test_display_manager_rotation tests.test_mode_switch_rotation
```

### Step 5: Commit

```bash
git add DisplayManager.py mode_switch.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py
git commit -m "refactor(display): separate image launch from readiness polling"
```

---

## Task 5: Replace GUI helper reconnect sleep with retry polling

**Files:**
- Modify: `Tinta4Plus.py`
- Test: `tests/test_tinta4plus_ui_state.py`

### Step 1: Introduce a reconnect polling helper

Add a helper such as:
```python
def _poll_helper_reconnect(self, timeout_s, interval_s):
    ...
```

Predicate:
- `self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT)` succeeds

Requirements:
- bounded timeout
- logs retries at debug level
- returns immediately on first success
- no direct `time.sleep(0.5)` call

### Step 2: Update `attempt_helper_restart()` to use the polling helper

Preserve existing success behavior:
- reconnect message
- event watcher start
- `_reconcile_from_live_state()`
- `self.root.after(500, self.check_ec_status)`

Preserve existing failure behavior:
- error log
- status update
- error dialog

### Step 3: Run focused tests

Run:
```bash
python3 -m unittest -v tests.test_tinta4plus_ui_state
```

### Step 4: Commit

```bash
git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
git commit -m "refactor(gui): poll for helper reconnect readiness"
```

---

## Task 6: Audit the tree and prove all production sleeps are gone

**Files:**
- Verify: `mode_switch.py`
- Verify: `DisplayManager.py`
- Verify: `Tinta4Plus.py`
- Verify: any helper modules added

### Step 1: Search for remaining production sleeps

Run:
```bash
rg -n "time\.sleep\(" -S mode_switch.py DisplayManager.py Tinta4Plus.py HelperDaemon.py
```

Expected:
- no results in production files
- tests may still use mocked timing or helper utilities as needed

### Step 2: Search for old delay constants

Run:
```bash
rg -n "XRANDR_APPLY_DELAY|IMAGE_DISPLAY_DELAY" -S .
```

Expected:
- no active production references
- if mentioned in docs/tests, update or delete as appropriate

### Step 3: Run the relevant automated suite

Run:
```bash
python3 -m unittest -v \
  tests.test_display_manager_rotation \
  tests.test_mode_switch_rotation \
  tests.test_mode_switch_state \
  tests.test_tinta4plus_ui_state \
  tests.test_logging_targets
```

Expected:
- PASS

### Step 4: Commit

```bash
git add DisplayManager.py mode_switch.py Tinta4Plus.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
git commit -m "refactor: remove blind sleeps from display switching"
```

---

## Task 7: Hardware verification with timestamp comparison

**Files:**
- Verify: runtime behavior only

### Step 1: Measure before/after using existing timestamped logs

Use `/tmp/TintaHelper.log` and current runtime logs to compare:
- switch-to-E-Ink start → `Now using E-Ink`
- switch-to-OLED start → `Now using OLED`
- helper prep durations
- convergence durations

### Step 2: Run repeated live roundtrips

Run several times:
```bash
python3 toggle-eink.py
python3 toggle-eink.py
```

Collect at least:
- 5 successful E-Ink switches
- 5 successful OLED switches

### Step 3: Verify readiness behavior is correct

Confirm:
- no regression in final active output
- no regression in theme switching
- no regression in touch/input remapping
- no new hangs from unbounded polls
- logs show timeout-based failures instead of silent waiting

### Step 4: Verify sleep removal did not increase flakiness

Check for:
- more `BadMatch` churn
- incomplete privacy-image behavior
- helper reconnect failures
- stale frontlight state

### Step 5: Final review

Run:
```bash
git diff -- DisplayManager.py mode_switch.py Tinta4Plus.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
```

Confirm the diff:
- removes blind sleeps
- adds bounded polling only
- does not introduce background threads or uncontrolled concurrency

### Step 6: Final commit if needed

```bash
git add DisplayManager.py mode_switch.py Tinta4Plus.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py docs/plans/2026-04-04-remove-blind-sleeps-with-readiness-polls.md
git commit -m "docs(plan): replace blind sleeps with readiness polling"
```

---

## Design constraints for implementation

- Prefer **observable system state** over elapsed time.
- Every poll must have a **timeout** and a **clear log message** on timeout.
- No unbounded retries.
- Keep xrandr operations serialized.
- Do not add threads unless tests prove they are necessary.
- Use the smallest number of new abstractions needed.
- If an operation has no trustworthy readiness signal, make that explicit in code and use the narrowest bounded fallback possible.
- Preserve current error-handling and rollback semantics unless a test is updated deliberately.
