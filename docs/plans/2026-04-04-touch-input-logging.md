# Touch Input Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add INFO-level logging for touch/input X11 commands and input-mode decisions so future touch failures can be diagnosed from normal logs.

**Architecture:** Extend the existing `mode_switch.py` XInput helper layer rather than adding new runtime paths. Keep `_run_xinput(...)` responsible for exact command execution logging, and keep `_apply_input_mode(...)` responsible for logging device matching and enable/disable/map decisions.

**Tech Stack:** Python 3, `subprocess`, `logging`, `unittest`, `unittest.mock`.

---

### Task 1: Add failing logging tests for `_run_xinput(...)`

**Files:**
- Modify: `tests/test_mode_switch_input_mode.py`
- Modify: `mode_switch.py`

**Step 1: Write the failing tests**
- Add a test proving `_run_xinput(...)` logs the command before execution and logs success for a successful `subprocess.run(...)` result.
- Add a test proving `_run_xinput(...)` logs a detailed failure message for a `CalledProcessError`.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: FAIL because the new log assertions are not satisfied.

**Step 3: Write minimal implementation**
- Update `_run_xinput(...)` to log `xinput <args>` at INFO before execution.
- On success, log success and trimmed stdout if present.
- On failure, log command plus available stderr/stdout details.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: PASS.

### Task 2: Add failing logging tests for `_apply_input_mode(...)`

**Files:**
- Modify: `tests/test_mode_switch_input_mode.py`
- Modify: `mode_switch.py`

**Step 1: Write the failing tests**
- Add a test proving `_apply_input_mode(...)` logs matched device groups, target output, and the final success summary.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: FAIL because the summary log does not exist yet.

**Step 3: Write minimal implementation**
- Add INFO-level summary logging for matched device groups, target output, enable IDs, disable IDs, and final result.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: PASS.

### Task 3: Focused verification

**Files:**
- Verify: `mode_switch.py`
- Verify: `tests/test_mode_switch_input_mode.py`

**Step 1: Run focused tests**
Run: `python -m unittest tests.test_mode_switch_input_mode -v`
Expected: PASS.

**Step 2: Review diff**
Run: `git diff -- mode_switch.py tests/test_mode_switch_input_mode.py docs/plans/2026-04-04-touch-input-logging-design.md docs/plans/2026-04-04-touch-input-logging.md`
Expected: logging-only production changes plus tests/docs.
