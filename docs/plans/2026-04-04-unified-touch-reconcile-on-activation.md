# Unified Touch Reconcile On Activation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify touchscreen health-check/reset behavior behind one shared reconciler and invoke it consistently after mode switches, orientation changes, lid-driven rotation, and when either app window becomes active.

**Architecture:** Keep low-level xinput probing/remap logic in `mode_switch.py`, but replace scattered `ensure_touch_available(...)` policy calls with a single shared coordinator that can either use an explicit target (`eink`/`oled`) or derive the current target from live display state. In `Tinta4Plus.py`, all GUI-triggered touch recovery paths should call that one coordinator, with a debounced activation hook bound to both the root window and the floating refresh button window.

**Tech Stack:** Python 3, tkinter, X11/XInput (`xinput`), `unittest`, `unittest.mock`.

---

### Task 1: Add a single shared touch reconciler in `mode_switch.py`

**Files:**
- Modify: `mode_switch.py`
- Modify: `tests/test_mode_switch_input_mode.py`

**Checklist:**
- [ ] Add failing tests for a new public reconciler function in `tests/test_mode_switch_input_mode.py`.
- [ ] Cover explicit-target behavior: when called with `target="eink"`, it should delegate to `ensure_touch_available(logger, "eink")`.
- [ ] Cover derived-target behavior: when called without `target`, it should read live mode via `get_display_state(display_mgr)` and map `mode` to `eink` or `oled`.
- [ ] Cover skip behavior: when live mode is `mixed` or `unknown`, it should not call `ensure_touch_available(...)`.
- [ ] Cover logging behavior: include the reconciliation `reason` in logs for success/skip/failure paths.
- [ ] Run: `python -m unittest tests.test_mode_switch_input_mode -v`
- [ ] Verify the new tests fail because the reconciler does not exist yet.
- [ ] Implement the minimal reconciler in `mode_switch.py`.
- [ ] Keep `ensure_touch_available(...)` as the low-level retry helper; do not duplicate xinput logic.
- [ ] Return a small, simple result contract that callers can use consistently (for example: `True` for healthy/recovered, `False` for failed or skipped), and document it with the function behavior/tests.
- [ ] Re-run: `python -m unittest tests.test_mode_switch_input_mode -v`
- [ ] Confirm the test module passes.

### Task 2: Replace switch-path touch policy with the shared reconciler

**Files:**
- Modify: `mode_switch.py`
- Modify: `tests/test_mode_switch_rotation.py`

**Checklist:**
- [ ] Add failing tests proving `switch_to_eink(...)` calls the shared reconciler once after successful input remap/orientation work.
- [ ] Add failing tests proving `switch_to_oled(...)` calls the shared reconciler once after successful input remap/orientation work.
- [ ] Assert these switch paths pass an explicit target (`"eink"` or `"oled"`) plus a useful reason string.
- [ ] Assert recovery remains warning-only so a successful switch still returns success even if touch recovery fails.
- [ ] Run: `python -m unittest tests.test_mode_switch_rotation -v`
- [ ] Verify the new tests fail before implementation.
- [ ] Update `switch_to_eink(...)` to call the shared reconciler instead of calling `ensure_touch_available(...)` directly.
- [ ] Update `switch_to_oled(...)` the same way.
- [ ] Preserve existing ordering around `_apply_input_mode(...)` and `apply_stored_orientation(...)`.
- [ ] Re-run: `python -m unittest tests.test_mode_switch_rotation -v`
- [ ] Confirm the switch-flow tests pass.

### Task 3: Replace GUI orientation/lid touch policy with the shared reconciler

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

**Checklist:**
- [ ] Add failing GUI tests proving `on_orientation_toggled(...)` calls the shared reconciler rather than directly calling `ensure_touch_available(...)`.
- [ ] Verify the orientation path still re-applies `_apply_input_mode(...)` first, then runs reconciliation.
- [ ] Add failing GUI tests proving `_reconcile_from_live_state(...)` uses the same shared reconciler for the lid-driven E-Ink rotation path.
- [ ] Run: `python -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Verify the new tests fail before implementation.
- [ ] Update `on_orientation_toggled(...)` to route touch recovery through the shared reconciler.
- [ ] Update `_reconcile_from_live_state(...)` to route touch recovery through the shared reconciler.
- [ ] Remove now-redundant direct `ensure_touch_available(...)` policy calls from GUI logic.
- [ ] Re-run: `python -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Confirm the GUI state tests pass.

### Task 4: Add debounced window-activation touch reconciliation for both windows

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

**Checklist:**
- [ ] Add failing tests for a shared GUI activation handler that triggers touch reconciliation when the main window becomes active.
- [ ] Add failing tests for the same behavior when the floating refresh button window becomes active.
- [ ] Add failing tests proving activation derives the current target from live display state rather than forcing `eink` or `oled`.
- [ ] Add failing tests proving `mixed`/`unknown` modes are skipped cleanly.
- [ ] Add failing tests for debounce/throttle behavior so rapid duplicate focus events do not spam repeated reconciliations.
- [ ] Run: `python -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Verify the activation tests fail before implementation.
- [ ] Add a single GUI helper in `Tinta4Plus.py` for activation-triggered touch reconciliation.
- [ ] Bind the main `root` window to that helper on activation/focus.
- [ ] Bind the floating refresh button `Toplevel` window to that same helper when it is created.
- [ ] Keep the floating button binding lifecycle-safe so destroyed/recreated windows do not leave stale references.
- [ ] Implement a short debounce in the GUI helper so focus changes between widgets/windows do not trigger repeated xinput checks.
- [ ] Re-run: `python -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Confirm the activation tests pass.

### Task 5: Clean up imports/call sites and verify only one policy path remains

**Files:**
- Modify: `mode_switch.py`
- Modify: `Tinta4Plus.py`
- Verify: `tests/test_mode_switch_input_mode.py`
- Verify: `tests/test_mode_switch_rotation.py`
- Verify: `tests/test_tinta4plus_ui_state.py`

**Checklist:**
- [ ] Review `Tinta4Plus.py` imports and replace any stale direct `ensure_touch_available` usage with the shared reconciler where appropriate.
- [ ] Review `mode_switch.py` and confirm there is one canonical policy entry point for touch reconciliation.
- [ ] Confirm low-level helpers remain DRY: `_apply_input_mode(...)`, `_is_touch_healthy_for_target(...)`, `ensure_touch_available(...)`, and the new reconciler each have a distinct responsibility.
- [ ] Run: `rg -n "ensure_touch_available|reconcile_touch|_apply_input_mode" Tinta4Plus.py mode_switch.py tests`
- [ ] Inspect the output and confirm policy decisions are centralized rather than duplicated.

### Task 6: Focused verification

**Files:**
- Verify: `mode_switch.py`
- Verify: `Tinta4Plus.py`
- Verify: `tests/test_mode_switch_input_mode.py`
- Verify: `tests/test_mode_switch_rotation.py`
- Verify: `tests/test_tinta4plus_ui_state.py`

**Checklist:**
- [ ] Run the focused automated tests:
```bash
python -m unittest \
  tests.test_mode_switch_input_mode \
  tests.test_mode_switch_rotation \
  tests.test_tinta4plus_ui_state -v
```
- [ ] Confirm all focused tests pass.
- [ ] Review the final diff:
```bash
git diff -- mode_switch.py Tinta4Plus.py tests/test_mode_switch_input_mode.py tests/test_mode_switch_rotation.py tests/test_tinta4plus_ui_state.py docs/plans/2026-04-04-unified-touch-reconcile-on-activation.md
```
- [ ] Confirm the diff contains only the shared touch reconciler refactor, activation hook, debounce logic, and regression tests.
- [ ] If everything looks correct, hand off to implementation using `superpowers:executing-plans`.
