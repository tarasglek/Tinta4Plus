# Orientation Toggle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a GUI orientation button that shows live landscape/portrait state from `xrandr`, rotates the active internal display on demand, and re-applies the last app-selected orientation after OLED↔E-Ink switches.

**Architecture:** Add shared rotation query/apply helpers to `DisplayManager.py`, keep rotation re-application in the shared switch path in `mode_switch.py`, and keep UI labels/state in `Tinta4Plus.py`. Startup must sync from live `xrandr` without forcing changes; only post-click and post-switch flows should enforce the app-selected orientation.

**Tech Stack:** Python 3, tkinter, X11/Xorg, `xrandr`, existing `DisplayManager`, shared `mode_switch.py`, `unittest`/`unittest.mock`.

**Execution Requirement (commit-as-you-go):** Each completed task must be committed before starting the next task. Do not batch multiple tasks into one commit.

---

## Rules for execution

- [ ] Follow TDD for every task: write the failing test first, run it, implement the minimum fix, rerun the test.
- [ ] **Commit after each task before moving to the next one.**
- [ ] Keep the UX labels as `Landscape` and `Portrait`, but store raw `xrandr` values where helpful.
- [ ] Startup sync must read live `xrandr` state and must not force a rotation change.
- [ ] If a task uncovers unexpected behavior, update this checklist before continuing.

---

## Task 1: Add shared display rotation helpers

**Files:**
- [ ] Modify: `DisplayManager.py`
- [ ] Create: `tests/test_display_manager_rotation.py`

### Checklist
- [ ] Add failing tests for `DisplayManager` helpers that:
  - [ ] detect the currently active display from mocked `xrandr --query` output
  - [ ] parse active rotation for `eDP-1` / `eDP-2`
  - [ ] treat `normal` as landscape and `left` as portrait
  - [ ] reject or safely ignore unsupported rotations like `right` / `inverted`
- [ ] Add a failing test proving `set_display_rotation(display_name, rotation)` builds `xrandr --output <display> --rotate <rotation>`.
- [ ] Run: `python -m unittest tests.test_display_manager_rotation -v` and confirm it fails.
- [ ] Implement minimal helpers in `DisplayManager.py`, such as:
  - [ ] `get_active_display()`
  - [ ] `get_display_rotation(display_name)`
  - [ ] `set_display_rotation(display_name, rotation)`
- [ ] Invalidate the `xrandr` cache after successful rotation changes.
- [ ] Run: `python -m unittest tests.test_display_manager_rotation -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py
  git commit -m "feat(display): add rotation query and apply helpers"
  ```

---

## Task 2: Add shared orientation preference handling in mode switch logic

**Files:**
- [ ] Modify: `mode_switch.py`
- [ ] Create: `tests/test_mode_switch_rotation.py`

### Checklist
- [ ] Add failing tests for shared rotation helpers in `mode_switch.py` that:
  - [ ] load/save the last app-selected orientation preference
  - [ ] do nothing if no preference exists yet
  - [ ] apply the stored rotation to the active display after a successful switch
  - [ ] leave switching successful even if rotation application fails
- [ ] Run: `python -m unittest tests.test_mode_switch_rotation -v` and confirm it fails.
- [ ] Add minimal shared helpers in `mode_switch.py` for orientation preference persistence.
- [ ] Store only supported values: `normal` and `left`.
- [ ] After successful `switch_to_eink(...)`, apply stored orientation to the newly active output if present.
- [ ] After successful `switch_to_oled(...)`, apply stored orientation to the newly active output if present.
- [ ] Treat touch remapping after rotation as required, not optional.
- [ ] If rotation is applied after a switch, re-run `_apply_input_mode(...)` for the active target so touch mapping stays aligned.
- [ ] If a user-triggered rotation succeeds from the GUI, re-run `_apply_input_mode(...)` for the current target immediately after confirming the new rotation.
- [ ] Reuse existing `xinput map-to-output` behavior; do not add custom CTM rotation math unless hardware verification proves it is necessary.
- [ ] Keep touch-remap failures warning-only so successful display switching or rotation still returns success.
- [ ] Keep rotation failures warning-only so successful display switching still returns success.
- [ ] Run: `python -m unittest tests.test_mode_switch_rotation -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add mode_switch.py tests/test_mode_switch_rotation.py
  git commit -m "feat(mode-switch): preserve app-selected orientation across display switches"
  ```

---

## Task 3: Add GUI startup sync and orientation button behavior

**Files:**
- [ ] Modify: `Tinta4Plus.py`
- [ ] Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing GUI tests without creating a real Tk window for:
  - [ ] startup sync reads live `xrandr` orientation and updates the button label
  - [ ] no active display disables the orientation button
  - [ ] clicking the button toggles between `Landscape` and `Portrait`
  - [ ] a successful GUI rotation re-runs shared input mapping for the current mode
  - [ ] UI updates only after confirmed rotation state is re-read
  - [ ] failed rotation leaves the previous confirmed label intact
- [ ] Run: `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm the new tests fail.
- [ ] Add a new orientation button in the `Display Control` section of `Tinta4Plus.py`.
- [ ] Use labels:
  - [ ] `Orientation: Landscape`
  - [ ] `Orientation: Portrait`
- [ ] Add GUI helpers such as:
  - [ ] `sync_orientation_from_display_state()`
  - [ ] `on_orientation_toggled()`
- [ ] On startup/helper reconnect, call the orientation sync helper after display state sync.
- [ ] On successful button press:
  - [ ] rotate the active display
  - [ ] confirm the new live rotation
  - [ ] re-run shared input mapping for the current mode so touch stays aligned
  - [ ] save the orientation preference through shared logic
  - [ ] refresh the UI label/status/logging
- [ ] On failure, show/log an error and keep the last confirmed UI state.
- [ ] Run: `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat(ui): add orientation toggle with startup xrandr sync"
  ```

---

## Task 4: Ensure CLI/shared switch path honors orientation behavior

**Files:**
- [ ] Modify: `toggle-eink.py` only if needed
- [ ] Modify: `tests/test_mode_switch_rotation.py`

### Checklist
- [ ] Add a regression test proving the shared OLED↔E-Ink path applies stored orientation regardless of whether the switch is triggered from GUI or CLI.
- [ ] Confirm `toggle-eink.py` does not need duplicate rotation logic if shared mode-switch code already covers it.
- [ ] If settings loading needs a small extension, keep it minimal and shared.
- [ ] Run:
  - [ ] `python -m unittest tests.test_mode_switch_rotation -v`
  - [ ] `python -m unittest tests.test_mode_switch_state -v`
- [ ] Commit progress:
  ```bash
  git add toggle-eink.py mode_switch.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py
  git commit -m "test(cli): verify shared switch path honors orientation preference"
  ```

---

## Task 5: Focused verification

**Files:**
- [ ] Verify: `DisplayManager.py`
- [ ] Verify: `mode_switch.py`
- [ ] Verify: `Tinta4Plus.py`
- [ ] Verify: `tests/test_display_manager_rotation.py`
- [ ] Verify: `tests/test_mode_switch_rotation.py`
- [ ] Verify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Run the focused automated tests:
  ```bash
  python -m unittest \
    tests.test_display_manager_rotation \
    tests.test_mode_switch_rotation \
    tests.test_mode_switch_state \
    tests.test_tinta4plus_ui_state -v
  ```
- [ ] Confirm all focused tests pass.
- [ ] Run a manual verification on hardware:
  ```bash
  xrandr --query
  python Tinta4Plus.py
  ./toggle-eink.py
  xrandr --query
  ```
- [ ] Manually verify:
  - [ ] startup button matches current live orientation
  - [ ] button toggles active display between landscape and portrait
  - [ ] switching OLED↔E-Ink preserves the last app-selected orientation
  - [ ] touch/input is remapped after every successful rotation
  - [ ] touch/input remains correctly mapped after rotation
  - [ ] failures, if any, leave the UI showing the last confirmed state
- [ ] Review the diff:
  ```bash
  git diff -- DisplayManager.py mode_switch.py Tinta4Plus.py toggle-eink.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
  ```
- [ ] Commit final verification or cleanup if needed:
  ```bash
  git add DisplayManager.py mode_switch.py Tinta4Plus.py toggle-eink.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
  git commit -m "test: verify orientation toggle behavior"
  ```

---

## Commit plan (required)

- [ ] Commit 1: shared display rotation query/apply helpers
- [ ] Commit 2: mode-switch orientation preference persistence and re-apply logic
- [ ] Commit 3: GUI orientation button and startup sync behavior
- [ ] Commit 4: shared-path CLI regression coverage
- [ ] Commit 5: verification/cleanup only if needed
