# Lower Scale Reset on Target Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make display enabling automatically apply an intermediate scale of `1.0` on the target display before applying a lower requested scale, preventing X/XFCE clipping when switching from a larger scale to a smaller one.

**Architecture:** Keep the fix centralized in `DisplayManager.enable_display()` so both GUI and CLI mode switches inherit the workaround automatically. Add one helper that can read a display's current effective scale from live `xrandr` state, plus one helper that builds/applies a single scale configuration for a target output. `enable_display()` should compare the target output's current effective scale with the requested scale and only do the two-step `1.0 -> target` flow when the requested scale is lower.

**Tech Stack:** Python 3, X11/XRandR (`xrandr`), existing `DisplayManager`, `unittest` / `unittest.mock`

---

## Task 1: Add failing tests for lower-scale reset behavior

**Files:**
- Modify: `tests/test_display_manager_rotation.py`
- Verify: `DisplayManager.py`

- [ ] Add a failing test proving lowering scale on the target display triggers two applies on that same target output.
  - Example scenario: current effective scale `1.9`, requested scale `1.5`, target display `eDP-1`
  - Expect first xrandr apply to target `eDP-1` at `1.0`
  - Expect second xrandr apply to target `eDP-1` at `1.5`
- [ ] Add a failing test proving increasing scale still applies only once.
  - Example scenario: current effective scale `1.5`, requested scale `1.9`
  - Expect one xrandr apply only
- [ ] Add a failing test proving unknown current scale falls back to direct apply.
  - Example scenario: current scale cannot be parsed
  - Expect one xrandr apply only
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm the tests fail for the expected reason: missing lower-scale reset orchestration in `DisplayManager`.

---

## Task 2: Add scale parsing and one-shot apply helpers in `DisplayManager`

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Add `get_effective_display_scale(self, display_name)`.
  - Read live `xrandr` output via `_get_xrandr_output()`
  - Parse the named connected display conservatively
  - Return the app-convention scale (`1.9`, `1.5`, etc.) when it can be determined
  - Return `None` when parsing is ambiguous
- [ ] Add `_apply_display_scale(self, display_name, scale=None)`.
  - Build exactly one `xrandr --output ...` command for the passed target display
  - For `None` or `1.0`, apply native mode, native panning, and `--scale 1x1`
  - For non-1.0 scales, keep the current inverted xrandr scale logic and panning calculation
  - Invalidate the xrandr cache after a successful apply
  - Return `True` or `False`
- [ ] Ensure the helper always acts on the passed `display_name` and never on some other currently active display.
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm failures, if any remain, are now only about the missing `enable_display()` orchestration.

---

## Task 3: Teach `enable_display()` to do `1.0 -> target` only when lowering scale

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Update `enable_display()` to compute whether the requested scale is lower than the target display's current effective scale.
  - Only consider this when `scale` is not `None` and not `1.0`
  - Compare against the **target display name being enabled**
- [ ] If the requested scale is lower, apply `1.0` on the target display first.
- [ ] After the temporary `1.0` reset, apply the final requested scale on that same target display.
- [ ] If the current scale is unknown, skip the workaround and apply the requested scale directly.
- [ ] Preserve existing verification behavior after enable.
  - invalidate xrandr cache
  - wait for X11 to settle
  - verify with `is_display_active(display_name)`
  - keep logging consistent
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm the focused tests pass.
- [ ] Commit:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py
  git commit -m "fix(display): reset target output before lowering scale"
  ```

---

## Task 4: Verify shared OLED/E-Ink flows inherit the centralized fix

**Files:**
- Verify: `mode_switch.py`
- Verify: `toggle-eink.py`
- Verify: `Tinta4Plus.py`
- Optional Test: `tests/test_mode_switch_state.py`

- [ ] Confirm shared switch paths still call `display_mgr.enable_display(..., scale=scale)` and do not duplicate scale-reset logic.
- [ ] Optionally add a light regression test proving the shared mode-switch path still passes the requested scale through to `DisplayManager` unchanged.
- [ ] Do **not** duplicate low-level xrandr sequencing tests outside `DisplayManager`.
- [ ] Run:
  ```bash
  python -m unittest tests.test_mode_switch_state tests.test_mode_switch_rotation -v
  ```
- [ ] Confirm the shared-flow tests pass.

---

## Task 5: Final verification before claiming success

**Files:**
- Verify: `DisplayManager.py`
- Verify: `tests/test_display_manager_rotation.py`
- Verify: any updated shared-flow tests

- [ ] Run the full relevant automated test set:
  ```bash
  python -m unittest \
    tests.test_display_manager_rotation \
    tests.test_mode_switch_state \
    tests.test_mode_switch_rotation \
    tests.test_tinta4plus_ui_state -v
  ```
- [ ] Confirm all relevant tests pass.
- [ ] Review the final diff:
  ```bash
  git diff -- DisplayManager.py tests/test_display_manager_rotation.py tests/test_mode_switch_state.py tests/test_mode_switch_rotation.py
  ```
- [ ] Confirm the diff only contains the intended lower-scale reset logic and focused regression coverage.
- [ ] Manually verify on hardware.
  - [ ] Reproduce a larger-to-smaller switch such as `1.9 -> 1.5`
  - [ ] Confirm clipping no longer happens
  - [ ] Confirm the temporary reset is applied on the target display being enabled
  - [ ] Confirm increasing scale still behaves normally
- [ ] Commit final verified state if needed:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py tests/test_mode_switch_state.py tests/test_mode_switch_rotation.py
  git commit -m "fix(display): avoid clipping when lowering output scale"
  ```
