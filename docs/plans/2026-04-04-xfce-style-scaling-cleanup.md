# XFCE-Style Scaling Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all active xrandr scaling code with XFCE-style transform-based scaling for both OLED and E-Ink, and remove the temporary `1.0 -> target` reset hack entirely.

**Architecture:** Keep scaling centralized in `DisplayManager.py` so GUI and CLI mode-switch flows continue to delegate to one implementation. Preserve the current target-state/verification structure, but change it to generate XFCE-style `--transform` commands instead of `--scale`, and remove all active-code/test leftovers tied to the old lower-scale reset workaround.

**Tech Stack:** Python 3, X11/XRandR (`xrandr`), existing `DisplayManager`, `mode_switch.py`, `unittest`, `unittest.mock`

---

## Task 1: Add failing tests for XFCE-style transform scaling

**Files:**
- Modify: `tests/test_display_manager_rotation.py`
- Verify: `DisplayManager.py`

- [ ] Add a failing test proving `_apply_display_scale("eDP-1", scale=1.5)` generates an `xrandr` command with:
  - `--mode 2880x1800`
  - `--transform 0.6666666666666666,0,0,0,0.6666666666666666,0,0,0,1`
  - `--panning 1920x1200`
  - `--fb 1920x1200`
  - and **does not** include `--scale`
- [ ] Add a failing test proving `finalize_single_display("eDP-2", scale=1.75)` generates an `xrandr` command with:
  - `--mode 2560x1600`
  - `--transform 0.5714285714285714,0,0,0,0.5714285714285714,0,0,0,1`
  - `--panning 1463x915`
  - `--fb 1463x915`
  - and **does not** include `--scale`
- [ ] Add a failing test proving `enable_display("eDP-1", scale=1.5)` uses transform-based activation and does **not** include `--fb`
- [ ] Update any existing command-shape tests that still assert `--scale`
- [ ] Remove or rewrite tests whose only purpose is to verify the `1.0 -> target` reset workaround
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm the failures are specifically about command generation still using `--scale` or reset-hack assumptions

## Task 2: Refactor target-state generation to describe transform scaling clearly

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Inspect `_build_display_target_state(display_name, scale=None)` and identify all fields that still imply old `--scale` semantics
- [ ] Replace those active-code field names with transform-oriented names, or add new transform-oriented fields and delete obsolete ones
- [ ] Keep the requested scale semantics unchanged:
  - app scale `1.0` means native/unscaled
  - app scale `> 1.0` means larger UI / smaller logical desktop
- [ ] Keep logical dimension math based on native size divided by requested scale, rounded up with `math.ceil(...)`
- [ ] Store enough target-state data to build XFCE-style transforms deterministically for both outputs
- [ ] Update target-state tests so they assert the transform coefficients and logical dimensions, not `xrandr_scale_x/y`
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation.DisplayManagerScalingTests -v
  ```
- [ ] Confirm the target-state tests pass before moving on

## Task 3: Replace all active `--scale` command generation with XFCE-style `--transform`

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Update `_apply_display_target_state(target_state)` to build:
  ```bash
  xrandr --output <display> --mode <native> --transform <a,0,0,0,a,0,0,0,1> --panning <logical> --fb <logical>
  ```
- [ ] For native/unscaled state, ensure the transform is the identity matrix:
  - `--transform 1,0,0,0,1,0,0,0,1`
- [ ] Update `_apply_display_scale(display_name, scale=None)` to use the new target-state fields without any `--scale` fallback for known displays
- [ ] Update `_activate_display_transition_safe(display_name, scale=None)` to use `--transform` and `--mode`, and to omit `--fb` intentionally
- [ ] Keep unknown-display fallback behavior as `xrandr --output <display> --auto`
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm all command-generation tests now pass with `--transform`
- [ ] Commit:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py
  git commit -m "refactor(display): use xfce-style transform scaling"
  ```

## Task 4: Remove the lower-scale reset hack and any active-code leftovers

**Files:**
- Modify: `DisplayManager.py`
- Modify: `tests/test_display_manager_rotation.py`
- Verify: `docs/plans/2026-04-04-lower-scale-reset-on-target-display.md`

- [ ] Remove any helper whose only job is resetting the target display to native before retry
- [ ] Remove any `enable_display()` orchestration that applies `1.0` before the requested target scale
- [ ] Remove dead parsing/branching that exists only to support the reset workaround if it is no longer needed
- [ ] Delete or rewrite tests that expect multiple applies when lowering scale
- [ ] Leave historical plan docs untouched unless asked; do **not** treat them as runtime leftovers
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm no active code or tests still enforce the reset hack
- [ ] Commit:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py
  git commit -m "fix(display): remove lower-scale reset hack"
  ```

## Task 5: Verify shared OLED and E-Ink switching paths still inherit the cleanup

**Files:**
- Verify: `mode_switch.py`
- Verify: `toggle-eink.py`
- Verify: `Tinta4Plus.py`
- Test: `tests/test_mode_switch_state.py`
- Test: `tests/test_mode_switch_rotation.py`

- [ ] Confirm shared switch paths still call `display_mgr.enable_display(..., scale=scale)` and `display_mgr.finalize_single_display(..., scale=scale)`
- [ ] Confirm no GUI or CLI path duplicates low-level transform logic outside `DisplayManager.py`
- [ ] Add or update only light regression coverage if needed to prove shared flows still pass the configured scale through unchanged
- [ ] Run:
  ```bash
  python -m unittest tests.test_mode_switch_state tests.test_mode_switch_rotation -v
  ```
- [ ] Confirm shared-flow tests pass without needing any reset-specific logic

## Task 6: Final verification before claiming cleanup is complete

**Files:**
- Verify: `DisplayManager.py`
- Verify: `tests/test_display_manager_rotation.py`
- Verify: `tests/test_mode_switch_state.py`
- Verify: `tests/test_mode_switch_rotation.py`

- [ ] Run the full relevant automated suite:
  ```bash
  python -m unittest \
    tests.test_display_manager_rotation \
    tests.test_mode_switch_state \
    tests.test_mode_switch_rotation \
    tests.test_tinta4plus_ui_state -v
  ```
- [ ] Review the final active-code diff:
  ```bash
  git diff -- DisplayManager.py tests/test_display_manager_rotation.py tests/test_mode_switch_state.py tests/test_mode_switch_rotation.py
  ```
- [ ] Confirm active code and tests contain:
  - one transform-based scaling model
  - no `--scale` assertions for known-display scaling paths
  - no `1.0 -> target` reset orchestration
  - no misleading helper names/comments in active code
- [ ] Manually verify on hardware:
  - switch to OLED with non-1.0 scaling
  - switch to E-Ink with non-1.0 scaling
  - lower scale and raise scale without clipping
  - confirm behavior matches the `fix-oled.sh` model
- [ ] Commit final verified state if needed:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py tests/test_mode_switch_state.py tests/test_mode_switch_rotation.py
  git commit -m "fix(display): unify scaling around xfce-style transforms"
  ```
