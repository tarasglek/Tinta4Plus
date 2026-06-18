# Touch Recovery After Rotate and Switch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect when the expected touch stack is disabled after display rotate/switch operations and re-apply the shared input mode automatically.

**Architecture:** Add small shared helpers in `mode_switch.py` to identify expected touch devices for the active target and detect whether any of them are enabled. Build a shared recovery helper that re-runs `_apply_input_mode(...)` and verifies the result. Invoke that helper after successful OLED/E-Ink switches and after successful GUI orientation toggles.

**Tech Stack:** Python 3, X11/XInput (`xinput`), tkinter, `unittest`, `unittest.mock`.

---

### Task 1: Add failing tests for touch-health detection helpers

**Files:**
- Modify: `tests/test_mode_switch_input_mode.py`
- Modify: `mode_switch.py`

**Step 1: Write the failing tests**
- Add a test for a helper that returns expected device IDs for target `eink` from matched ITE devices.
- Add a test for a helper that returns expected device IDs for target `oled` from matched Wacom devices.
- Add a test for a helper that reports touch healthy when at least one expected device is enabled.
- Add a test for a helper that reports touch busted when all expected devices are disabled.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: FAIL because the new helpers do not exist yet.

**Step 3: Write minimal implementation**
- Add helper(s) in `mode_switch.py` to:
  - collect expected device IDs for a target
  - inspect `Device Enabled` state for those devices
  - report healthy vs busted
- Keep implementation small and fully shared.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: PASS.

### Task 2: Add failing tests for shared recovery helper

**Files:**
- Modify: `tests/test_mode_switch_input_mode.py`
- Modify: `mode_switch.py`

**Step 1: Write the failing tests**
- Add a test proving recovery does nothing when touch is already healthy.
- Add a test proving recovery re-runs `_apply_input_mode(target)` when touch is busted.
- Add a test proving recovery verifies again after re-applying input mode.
- Add a test proving recovery logs a warning if touch is still busted after retry.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: FAIL because the recovery helper does not exist yet.

**Step 3: Write minimal implementation**
- Add a shared helper such as `ensure_touch_available(logger, target)`.
- It should:
  - check whether touch is healthy for the target
  - if busted, log warning and re-run `_apply_input_mode(target)`
  - verify again once
  - log final success or persistent failure
- Keep recovery bounded to one retry for now.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_mode_switch_input_mode.ApplyInputModeTests -v`
Expected: PASS.

### Task 3: Hook recovery into shared switch paths

**Files:**
- Modify: `mode_switch.py`
- Modify: `tests/test_mode_switch_rotation.py`

**Step 1: Write the failing tests**
- Add a test proving `switch_to_eink(...)` invokes touch recovery after successful input-mode application.
- Add a test proving `switch_to_oled(...)` invokes touch recovery after successful input-mode application.
- Keep failures warning-only so successful display switching still returns success.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_mode_switch_rotation -v`
Expected: FAIL because recovery is not called yet.

**Step 3: Write minimal implementation**
- In `switch_to_eink(...)`, call the shared recovery helper after `_apply_input_mode("eink")` and any stored orientation re-apply path.
- In `switch_to_oled(...)`, call the shared recovery helper after `_apply_input_mode("oled")` and any stored orientation re-apply path.
- Keep recovery warning-only.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_mode_switch_rotation -v`
Expected: PASS.

### Task 4: Hook recovery into GUI orientation toggle

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

**Step 1: Write the failing tests**
- Add a test proving a successful UI orientation toggle invokes shared touch recovery for the current target.
- Keep existing input-remap behavior assertions intact.

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_tinta4plus_ui_state -v`
Expected: FAIL because orientation toggle only re-applies input mode today.

**Step 3: Write minimal implementation**
- Import and call the shared recovery helper after successful orientation remap.
- Preserve current UI success/failure behavior.

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_tinta4plus_ui_state -v`
Expected: PASS.

### Task 5: Focused verification

**Files:**
- Verify: `mode_switch.py`
- Verify: `Tinta4Plus.py`
- Verify: `tests/test_mode_switch_input_mode.py`
- Verify: `tests/test_mode_switch_rotation.py`
- Verify: `tests/test_tinta4plus_ui_state.py`

**Step 1: Run focused tests**
Run:
```bash
python -m unittest \
  tests.test_mode_switch_input_mode \
  tests.test_mode_switch_rotation \
  tests.test_tinta4plus_ui_state -v
```
Expected: PASS.

**Step 2: Review diff**
Run:
```bash
git diff -- mode_switch.py Tinta4Plus.py tests/test_mode_switch_input_mode.py tests/test_mode_switch_rotation.py tests/test_tinta4plus_ui_state.py docs/plans/2026-04-04-touch-recovery-after-rotate-and-switch.md
```
Expected: shared touch recovery changes plus tests only.
