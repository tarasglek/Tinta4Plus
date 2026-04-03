# Common Touch Mapping on Display Switch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the shared OLED↔E-Ink switch path manage both input enablement and X11 output mapping so touch/stylus devices work consistently in GUI and CLI.

**Architecture:** Extend `mode_switch.py`'s existing XInput helpers so `_apply_input_mode(...)` both enables/disables device groups and maps the enabled group to the active output with `xinput map-to-output`. Keep failures warning-only so display switching remains resilient. Cover the change with focused unit tests around helper behavior and preserve the existing shared switch flow used by both `Tinta4Plus.py` and `toggle-eink.py`.

**Tech Stack:** Python 3, X11/Xorg, `xinput`, `xrandr`, `unittest`/`unittest.mock`

**Execution Requirement (commit-as-you-go):** Each completed task must be committed before starting the next task. Do not batch multiple tasks into one commit.

---

## Design Summary

- [ ] Keep the common-path ownership in `mode_switch.py`; do not duplicate input logic in GUI or CLI callers.
- [ ] Continue matching device families by name pattern:
  - E-Ink devices: `ITE Tech. Inc. ITE T-CON*`
  - OLED devices: `Wacom HID 537D*`
- [ ] For `target="eink"`:
  - enable all matching ITE devices
  - disable all matching Wacom devices not shared with ITE
  - map enabled ITE devices to `eDP-2`
- [ ] For `target="oled"`:
  - enable all matching Wacom devices
  - disable all matching ITE devices not shared with Wacom
  - map enabled Wacom devices to `eDP-1`
- [ ] Treat input failures as warning-only; do not abort successful display mode changes because `xinput` mapping failed.
- [ ] Prefer `xinput map-to-output` over hand-written CTM math in this change.
- [ ] Map all matching subdevices, not just the primary touch device, so pen/touch/eraser remain consistent.

## Files

- [ ] Modify: `mode_switch.py`
- [ ] Create or modify tests: `tests/test_mode_switch_input_mode.py`
- [ ] Optionally update docs after verification: `README.md` (known-bug wording only if warranted by verified behavior)

## Task 1: Add failing tests for common-path input mapping

**Files:**
- [ ] Test: `tests/test_mode_switch_input_mode.py`

### Checklist
- [ ] Add a focused test module for `mode_switch.py` input helpers.
- [ ] Add a failing test proving `_apply_input_mode(logger, "eink")`:
  - [ ] lists devices
  - [ ] enables matching ITE IDs
  - [ ] disables matching Wacom IDs
  - [ ] maps enabled ITE IDs to `eDP-2`
- [ ] Add a failing test proving `_apply_input_mode(logger, "oled")` maps enabled Wacom IDs to `eDP-1`.
- [ ] Add a failing test proving mapping failures make `_apply_input_mode(...)` return `False` without raising.
- [ ] Add a failing test proving no devices found returns `False` and logs/skips cleanly.
- [ ] Use mocking around `_list_xinput_devices`, `_set_input_enabled`, and the new mapping helper so tests stay deterministic.
- [ ] Run only the new test file to confirm it fails for the expected missing behavior.

### Suggested test command
- [ ] Run: `python -m unittest tests.test_mode_switch_input_mode -v`

## Task 2: Add XInput output-mapping helper(s)

**Files:**
- [ ] Modify: `mode_switch.py`

### Checklist
- [ ] Add a small helper such as `_map_input_to_output(logger, device_id, output_name)`.
- [ ] Implement it via `_run_xinput(logger, ["map-to-output", str(device_id), output_name])`.
- [ ] Return boolean success/failure rather than raising.
- [ ] Keep helper naming/style aligned with `_set_input_enabled(...)`.
- [ ] Do not add custom matrix math in this task.

## Task 3: Extend `_apply_input_mode(...)` to map enabled devices

**Files:**
- [ ] Modify: `mode_switch.py`

### Checklist
- [ ] Define output selection inside `_apply_input_mode(...)`:
  - [ ] `target="eink"` → output `DISPLAY_EINK`
  - [ ] `target="oled"` → output `DISPLAY_OLED`
- [ ] Keep the current device-group selection logic intact.
- [ ] After enabling target IDs, map each enabled target ID to the target output.
- [ ] Preserve current disable behavior for the non-target group.
- [ ] Aggregate failures across enable/disable/map steps into a final boolean result.
- [ ] Continue warning on unknown target and return `False`.
- [ ] Ensure an empty device list still logs/skips and returns `False`.
- [ ] Avoid changing `switch_to_eink(...)` / `switch_to_oled(...)` call sites beyond relying on the enhanced helper.

## Task 4: Verify unit tests pass

**Files:**
- [ ] Test: `tests/test_mode_switch_input_mode.py`
- [ ] Verify no unrelated tests need changes unless they assert helper internals

### Checklist
- [ ] Run the new test file until it passes.
- [ ] Run existing mode-switch related tests to guard against regressions.

### Suggested test commands
- [ ] Run: `python -m unittest tests.test_mode_switch_input_mode -v`
- [ ] Run: `python -m unittest tests.test_mode_switch_state -v`

## Task 5: Manual verification on real X11 hardware

**Files:**
- [ ] Verify runtime behavior only; no code changes unless a new issue is discovered

### Checklist
- [ ] Switch to E-Ink using the shared path: `./toggle-eink.py`
- [ ] Confirm monitor state: `xrandr --listmonitors`
- [ ] Confirm ITE devices are enabled:
  - [ ] `xinput list-props 13 | grep "Device Enabled"`
  - [ ] Repeat for other matching ITE IDs present on the machine
- [ ] Confirm enabled ITE device CTM is no longer identity after mapping:
  - [ ] `xinput list-props 13 | grep "Coordinate Transformation Matrix"`
- [ ] Test actual tapping on E-Ink.
- [ ] Switch back to OLED using the same shared path: `./toggle-eink.py`
- [ ] Confirm Wacom devices are enabled and mapped to `eDP-1`.
- [ ] Confirm ITE devices are disabled in OLED mode.
- [ ] Record any residual issue separately if taps still register with wrong coordinates even after `map-to-output`.

## Task 6: Optional documentation update

**Files:**
- [ ] Modify: `README.md` only if manual verification shows the known-bug statement is no longer accurate

### Checklist
- [ ] If touch mapping in scaled E-Ink mode is improved but not fully solved, keep the known-bug note and narrow its wording.
- [ ] If touch mapping is verified fixed in the tested setup, update the known-bug section accordingly.
- [ ] Do not claim universal hardware support; scope statements to the tested environment.

## Task 7: Final verification before completion

### Checklist
- [ ] Run all verification commands again before claiming success.
- [ ] Capture exact outputs for the passing tests and the XInput state checks.
- [ ] Confirm no GUI/CLI-specific code path duplicates input mapping logic.
- [ ] Review diff for `mode_switch.py` and the new test file only.

### Suggested verification commands
- [ ] `python -m unittest tests.test_mode_switch_input_mode tests.test_mode_switch_state -v`
- [ ] `git diff -- mode_switch.py tests/test_mode_switch_input_mode.py README.md`
- [ ] `xrandr --listmonitors`
- [ ] `xinput --list --short`

## Commit plan (required)

- [ ] Commit 1 (after Task 1): failing/passing tests for input mapping helper behavior
- [ ] Commit 2 (after Tasks 2-3): common-path input output-mapping implementation
- [ ] Commit 3 (after Tasks 4-7): verification and docs update only if verification warrants it
- [ ] Before opening/merging PR, ensure task order and commit order match (commit-as-you-go evidence).
