# RandR Full-State Transition Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor display switching so every OLED/E-Ink transition applies and verifies a complete XRandR target state, including framebuffer size, preventing clipped desktops caused by stale framebuffer state.

**Architecture:** Centralize all display-state math and XRandR application logic in `DisplayManager.py`. Introduce an explicit target-state representation that computes native mode, logical desktop size, xrandr transform, panning, and framebuffer together, then apply and verify that state deterministically. Keep `mode_switch.py` focused on higher-level mode orchestration, with display-state convergence delegated to `DisplayManager`.

**Tech Stack:** Python 3, X11/XRandR (`xrandr`), existing `DisplayManager` and `mode_switch` modules, `unittest` / `unittest.mock`

---

## Task 1: Document and encode the target state shape

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Add a small internal target-state representation in `DisplayManager.py`.
  - Keep it simple: dict or lightweight class with keys/fields for:
    - `display_name`
    - `native_width`
    - `native_height`
    - `requested_scale`
    - `xrandr_scale_x`
    - `xrandr_scale_y`
    - `logical_width`
    - `logical_height`
    - `panning_width`
    - `panning_height`
    - `framebuffer_width`
    - `framebuffer_height`
- [ ] Add one helper that computes this target state from `display_name` and requested app scale.
- [ ] Ensure native/unscaled state produces:
  - `--scale 1x1`
  - native logical size
  - native panning
  - native framebuffer
- [ ] Ensure scaled state produces one consistent logical size used for geometry, panning, and framebuffer.
- [ ] Add failing tests for the computed target-state values for:
  - native OLED
  - scaled OLED
  - scaled E-Ink
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm failures are only due to missing target-state helper behavior.

## Task 2: Refactor xrandr apply into full-state application

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Replace the current partial apply flow in `_apply_display_scale()` with a helper that applies the computed target state.
- [ ] Build xrandr commands from the target-state object, not from scattered branch math.
- [ ] Include framebuffer size in the apply path with `--fb`.
- [ ] Preserve current behavior for unknown displays by keeping the existing fallback path.
- [ ] Log the desired target state before running xrandr.
- [ ] Add failing tests asserting the xrandr command includes:
  - `--mode`
  - `--scale`
  - `--panning`
  - `--fb`
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm focused tests now pass or only fail on verification behavior not yet added.

## Task 3: Add post-apply verification of actual RandR state

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Add a helper that reads actual xrandr state after apply and extracts:
  - screen framebuffer size from the `Screen 0:` line
  - active output geometry for the target display
- [ ] Add a verification helper that compares actual state against the computed target state.
- [ ] Verification must confirm at minimum:
  - target display is active
  - framebuffer width/height are at least the expected logical width/height
  - active output geometry matches expected logical width/height
- [ ] Log mismatches in a structured way.
- [ ] Add failing tests for:
  - matching postcondition returns success
  - framebuffer too small returns failure
  - wrong output geometry returns failure
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm the verification tests pass.

## Task 4: Add one deterministic recovery path for mismatched state

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Add one recovery helper that resets the target display to a known-good native baseline.
  - Use the successful manual recovery shape:
    - native mode
    - `--scale 1x1`
    - panning reset
    - native framebuffer
- [ ] Update `enable_display()` so when post-apply verification fails due to framebuffer/output mismatch, it:
  - runs the baseline reset once
  - reapplies the target state once
  - verifies again
- [ ] Do not loop indefinitely.
- [ ] Preserve existing lower-scale-via-1.0 behavior unless the new full-state apply makes it redundant; if redundant, remove it deliberately and update tests.
- [ ] Add failing tests for:
  - one failed verification triggers one recovery attempt
  - second verification success returns `True`
  - repeated failure returns `False`
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Confirm the recovery-path tests pass.

## Task 5: Keep `mode_switch.py` orchestration thin and observable

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

- [ ] Confirm `mode_switch.py` continues to delegate display convergence to `display_mgr.enable_display(..., scale=...)`.
- [ ] Keep the new post-switch logging in `mode_switch.py` so switch-level logs still show:
  - `Screen 0:` state
  - active outputs
  - active monitors
- [ ] Do not duplicate framebuffer repair logic in `mode_switch.py`.
- [ ] Add/adjust tests only as needed to verify:
  - switch flows still call `enable_display()` once per transition step
  - post-switch snapshot logging still runs
- [ ] Run:
  ```bash
  python -m unittest tests.test_mode_switch_rotation -v
  ```
- [ ] Confirm the switch-flow tests pass.

## Task 6: Verify real switching scenarios in focused test runs

**Files:**
- Verify: `DisplayManager.py`
- Verify: `mode_switch.py`
- Verify: `tests/test_display_manager_rotation.py`
- Verify: `tests/test_mode_switch_rotation.py`

- [ ] Run the focused automated suite:
  ```bash
  python -m unittest \
    tests.test_display_manager_rotation \
    tests.test_mode_switch_rotation -v
  ```
- [ ] Review the diff:
  ```bash
  git diff -- DisplayManager.py mode_switch.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py
  ```
- [ ] Confirm the diff shows one coherent refactor toward full-state application and verification.
- [ ] Manually verify on hardware:
  - switch OLED native -> OLED scaled
  - switch OLED scaled -> lower OLED scaled
  - switch OLED -> E-Ink
  - switch E-Ink -> OLED
- [ ] After each transition, confirm:
  - no clipped desktop
  - framebuffer matches or exceeds logical output geometry
  - logs show desired state and resulting state
- [ ] Commit:
  ```bash
  git add DisplayManager.py mode_switch.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py
  git commit -m "fix(display): apply verified full RandR target state"
  ```

## Task 7: Optional cleanup if the old incremental logic becomes obsolete

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

- [ ] Re-evaluate whether the old special-case lower-scale reset logic is still needed once full-state apply plus verification exists.
- [ ] If full-state apply reliably covers that case, remove obsolete branching and simplify `enable_display()`.
- [ ] Update tests to validate the simpler contract.
- [ ] Run:
  ```bash
  python -m unittest tests.test_display_manager_rotation -v
  ```
- [ ] Commit cleanup separately:
  ```bash
  git add DisplayManager.py tests/test_display_manager_rotation.py
  git commit -m "refactor(display): simplify scale transition flow"
  ```

---

## Definition of Done

- [ ] `DisplayManager` computes one explicit target state per display apply.
- [ ] The apply path includes framebuffer management with `--fb`.
- [ ] Every display transition verifies postconditions against actual xrandr state.
- [ ] One deterministic recovery path exists for framebuffer/output mismatch.
- [ ] `mode_switch.py` stays orchestration-only and does not duplicate display repair logic.
- [ ] Focused automated tests pass.
- [ ] Manual hardware verification confirms no clipped desktop after repeated switching.
