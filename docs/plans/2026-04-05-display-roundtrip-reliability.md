# Display Roundtrip Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make one OLED ↔ E-Ink roundtrip reliable by refactoring mode-switch orchestration around an explicit critical display-convergence phase, while treating theme, DPMS, input, touch, and stored-orientation work as best-effort follow-up after convergence succeeds.

**Architecture:** Keep all low-level RandR target-state math and verification in `DisplayManager.py`, where `_build_display_target_state(...)`, activation, and final verification already live. Refactor `mode_switch.py` so each switch path is split into explicit phases: preparation, critical single-display convergence, best-effort post-success reconciliation, and must-run cleanup. Add one shared orchestration helper that converges to a single active display by calling existing `DisplayManager` primitives in a deterministic order and emitting useful mismatch diagnostics on failure.

**Tech Stack:** Python 3, `xrandr`, `subprocess`, `unittest`, `unittest.mock`.

---

## Scope Checklist

- [ ] Prioritize reliable display roundtrip over preserving every current side-effect ordering
- [ ] Keep helper protocol unchanged
- [ ] Keep GUI/CLI entrypoints unchanged
- [ ] Keep low-level display target-state construction in `DisplayManager.py`
- [ ] Refactor only mode-switch orchestration in `mode_switch.py`
- [ ] Make theme switching best-effort after display convergence succeeds
- [ ] Make input/touch/orientation reconciliation best-effort after display convergence succeeds
- [ ] Treat DPMS save/restore as best-effort post-success reconciliation
- [ ] Add regression tests for one successful OLED → E-Ink → OLED logical roundtrip flow
- [ ] Add tests for early failure when target display state does not converge

## Design Checklist

- [ ] Structure each switch flow into explicit phases
  - [ ] Phase 1: helper/hardware preparation
  - [ ] Phase 2: critical display convergence
  - [ ] Phase 3: best-effort post-success follow-up actions
  - [ ] Phase 4: must-run cleanup/final logging
- [ ] Give each phase its own `try/except` boundary
- [ ] Use `finally` for cleanup that must run regardless of success/failure
  - [ ] terminate privacy image process
  - [ ] release temporary state/resources
  - [ ] emit guarded end-of-switch diagnostics
- [ ] Ensure critical-phase failure returns switch failure immediately
- [ ] Ensure best-effort follow-up failures are warning-only and do not override convergence result
- [ ] Define one orchestration-level target description for `oled`
  - [ ] target output = `eDP-1`
  - [ ] other output = `eDP-2`
  - [ ] follow-up theme = `Adwaita-dark`
  - [ ] follow-up input/touch target = `oled`
  - [ ] snapshot reason = `switch_to_oled`
- [ ] Define one orchestration-level target description for `eink`
  - [ ] target output = `eDP-2`
  - [ ] other output = `eDP-1`
  - [ ] follow-up theme = `HighContrast`
  - [ ] follow-up input/touch target = `eink`
  - [ ] snapshot reason = `switch_to_eink`
- [ ] Define one deterministic convergence order for both targets
  - [ ] enable target output in transition-safe mode
  - [ ] disable non-target output
  - [ ] finalize compact single-display layout
  - [ ] fail fast if final verification does not converge
- [ ] Separate critical steps from non-critical steps
  - [ ] critical = display topology/scaling convergence via `DisplayManager`
  - [ ] non-critical = theme, DPMS, touch/input, stored orientation, frontlight polish
- [ ] Preserve ownership boundaries
  - [ ] `DisplayManager.py` owns low-level RandR state math and verification
  - [ ] `mode_switch.py` owns helper sequencing, follow-up policies, and cleanup

## Task 1: Add failing switch-ordering tests

**Files:**
- Modify: `tests/test_mode_switch_rotation.py`
- Modify: `tests/test_mode_switch_state.py` only if a shared helper contract belongs there

**Step 1: Write a failing test for OLED post-convergence ordering**

Add a test proving `switch_to_oled(...)` only runs best-effort follow-up work after critical display convergence succeeds.

Example assertions:
- critical display calls complete first
- theme/DPMS/input/orientation/touch hooks run only after convergence success
- if convergence fails, function returns `False`

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL because current flow still changes theme before convergence is proven.

**Step 3: Write a failing test for E-Ink post-convergence ordering**

Add the symmetric test for `switch_to_eink(...)`.

**Step 4: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL for the same reason.

**Step 5: Commit the tests**

```bash
git add tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py
git commit -m "test(display): cover post-converge switch ordering"
```

## Task 2: Add orchestration-level target helper(s)

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_state.py`

**Step 1: Write a failing test for orchestration target metadata**

Add tests for a helper such as `_build_switch_target(mode)` asserting exact fields for:
- mode name
- target output name
- other output name
- theme name
- touch/input target name
- snapshot/logging reason

Do **not** duplicate low-level transform/framebuffer math here.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_state.py`
Expected: FAIL because helper does not exist yet.

**Step 3: Write minimal implementation**

Add a small helper returning orchestration metadata for `oled` and `eink`, derived from existing constants in `mode_switch.py`.

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -q tests/test_mode_switch_state.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_state.py
git commit -m "refactor(display): add switch target metadata"
```

## Task 3: Centralize critical single-display convergence

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

**Step 1: Write a failing test for a shared convergence helper**

Add tests for a helper such as `_converge_single_display(display_mgr, logger, switch_target, scale)` proving it:
- enables the target output with `display_mgr.enable_display(...)`
- disables the non-target output with `display_mgr.disable_display(...)`
- finalizes the compact single-display layout with `display_mgr.finalize_single_display(...)`
- returns `False` if any critical step fails
- does not run any non-critical follow-up work itself

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL because helper does not exist yet.

**Step 3: Write minimal implementation**

Extract the critical display-only path from both switch functions into the shared convergence helper. Keep all target-state math delegated to `DisplayManager.py`.

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py
git commit -m "refactor(display): centralize single-display convergence"
```

## Task 4: Refactor OLED switch into explicit phases

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

**Step 1: Write a failing test for OLED convergence failure behavior**

Add a test proving that when critical convergence fails:
- `switch_to_oled(...)` returns `False`
- non-critical follow-up actions do not run
- success logging does not run
- privacy image cleanup still runs

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL under current structure.

**Step 3: Write minimal implementation**

Refactor `switch_to_oled(...)` into explicit phases:
1. helper/hardware preparation in its own `try/except`
2. critical convergence helper call in its own `try/except`
3. best-effort follow-up phase in its own `try/except`
4. must-run cleanup in `finally`

OLED policy:
- preparation may start privacy image, disable E-Ink in helper, and disable frontlight
- critical convergence failure returns `False`
- follow-up phase handles dark theme, DPMS restore, input mode, stored orientation, touch reconcile, snapshot logging
- privacy image teardown must happen in `finally`

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py
git commit -m "refactor(display): gate oled follow-ups on convergence"
```

## Task 5: Refactor E-Ink switch into explicit phases

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

**Step 1: Write a failing test for E-Ink convergence failure behavior**

Add a test proving that when critical convergence fails:
- `switch_to_eink(...)` returns `False`
- follow-up actions do not run after failed convergence
- success logging does not run
- no false-positive theme/DPMS post-success state is applied

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

Refactor `switch_to_eink(...)` to mirror the OLED structure:
1. helper/hardware preparation in its own `try/except`
2. critical convergence helper call in its own `try/except`
3. best-effort follow-up phase in its own `try/except`
4. must-run cleanup/logging in `finally`

E-Ink policy:
- preparation may enable helper E-Ink mode and optionally set frontlight brightness
- critical convergence failure returns `False`
- follow-up phase handles HighContrast theme, DPMS disable, input mode, stored orientation, touch reconcile, snapshot logging
- no early return may skip guarded final diagnostics

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py
git commit -m "refactor(display): gate eink follow-ups on convergence"
```

## Task 6: Tighten convergence failure logging

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

**Step 1: Write a failing test for convergence failure logging**

Add a test proving critical convergence failure logs:
- target mode (`oled` or `eink`)
- expected target output
- expected non-target output
- which critical step failed (`enable`, `disable`, or `finalize`)

If available from existing logs, include mismatch payload emitted by `DisplayManager` verification instead of recreating it in `mode_switch.py`.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

Improve failure logging in the shared convergence helper so switch-level diagnostics clearly identify the intended target and failed step while preserving `DisplayManager` as the owner of low-level mismatch details.

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -q tests/test_mode_switch_rotation.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py
git commit -m "chore(display): log convergence failure context"
```

## Task 7: End-to-end regression verification

**Files:**
- Verify only

**Step 1: Run focused unit tests**

Run:
```bash
python3 -m unittest -q \
  tests/test_mode_switch_rotation.py \
  tests/test_mode_switch_state.py \
  tests/test_tinta4plus_ui_state.py \
  tests/test_logging_targets.py
```
Expected: PASS.

**Step 2: Run one real CLI roundtrip**

Run:
```bash
python3 toggle-eink.py
python3 toggle-eink.py
```
Expected:
- first command switches to E-Ink or fails with explicit convergence diagnostics
- second command restores OLED without leaving HighContrast behind
- final `xrandr --query` shows only the intended target display active

**Step 3: Capture final live state**

Run:
```bash
xrandr --query
xrandr --listactivemonitors
xfconf-query -c xsettings -p /Net/ThemeName
```
Expected:
- OLED target: only `eDP-1` active, dark theme
- E-Ink target: only `eDP-2` active, HighContrast theme

**Step 4: Commit final refactor**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py tests/test_mode_switch_state.py
git commit -m "refactor(display): converge roundtrip switching reliably"
```

## Success Criteria Checklist

- [ ] A single OLED → E-Ink → OLED roundtrip works reliably
- [ ] Each switch path is structured as explicit phases with separate error handling
- [ ] Must-run cleanup executes via `finally` even when switch phases fail
- [ ] Theme no longer remains HighContrast on OLED after failed or partial OLED return path
- [ ] Switch functions do not report success when target display state failed to converge
- [ ] Critical display convergence is isolated from best-effort follow-up work
- [ ] `DisplayManager.py` remains the sole owner of low-level target-state math and verification
- [ ] Unit tests cover convergence success/failure ordering
- [ ] Live verification confirms final display and theme state after roundtrip
