# E-Ink Live State Reconcile Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every E-Ink-related trigger converge through one reconciler that ensures touch health, lid-close sleep inhibitor state, orientation policy, and UI state from live facts.

**Architecture:** Treat startup, reconnect, mode switches, lid/RandR invalidations, and window activation as dumb triggers that only request a live-state reconcile. Keep `Tinta4Plus.py` as the sole policy owner. `_reconcile_from_live_state()` should read the live facts, derive the desired E-Ink policy, apply only the minimal changes needed, and remain safe to call repeatedly.

**Tech Stack:** Python 3, tkinter, unittest, `systemd-inhibit`, existing `mode_switch.py` touch helpers.

---

## Reductionist state-machine policy

### Live facts the reconciler reads
- display mode: `oled | eink | mixed | unknown`
- lid state: `open | closed`
- active display and current rotation
- current inhibitor process status

### Desired policy derived from those facts
- If live mode is `eink`:
  - lid-close inhibitor must be running
  - E-Ink orientation must match lid policy
    - lid open -> landscape (`normal`)
    - lid closed -> portrait (`left`)
  - E-Ink touch must be usable after any needed orientation or mode correction
- If live mode is not `eink`:
  - lid-close inhibitor must not be running
  - no E-Ink-specific rotation or touch enforcement should run

### Trigger rule
The following code paths must not own policy. They should only request reconcile:
- helper startup success
- helper reconnect success
- successful mode switch
- lid invalidation
- RandR invalidation
- window activation/focus events

### Code comments requirement
Add a short comment block above `_reconcile_from_live_state()` explaining:
1. it is the single policy owner for live E-Ink usability
2. all triggers should feed into it rather than duplicating touch/inhibitor policy elsewhere
3. it is intentionally idempotent and may be called often

---

## Checklist

### Task 1: Add failing orchestration tests for the single-reconciler design
- [ ] Modify `tests/test_tinta4plus_ui_state.py`
- [ ] Add a failing test proving `initialize_helper()` requests `_reconcile_from_live_state()` immediately after successful helper connection
- [ ] Add a failing test proving `attempt_helper_restart()` requests `_reconcile_from_live_state()` immediately after successful reconnect
- [ ] Add a failing test proving successful `on_eink_toggled()` -> `switch_to_eink(...)` requests `_reconcile_from_live_state()`
- [ ] Add a failing test proving window activation requests `_reconcile_from_live_state()` instead of directly owning E-Ink touch policy
- [ ] Add/adjust tests so non-E-Ink activation remains a no-op or cheap no-op through the reconciler rather than separate policy branches
- [ ] Run `python3 -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Verify the new tests fail for the expected orchestration reason

**Notes:**
- Prefer orchestration assertions with mocks over deep implementation coupling.
- Keep tests focused on “who owns policy” rather than incidental UI details.

### Task 2: Make all relevant triggers request the reconciler and nothing else
- [ ] Modify `Tinta4Plus.py`
- [ ] In `initialize_helper()`, after successful helper connection and watcher setup, call `_reconcile_from_live_state()`
- [ ] In `attempt_helper_restart()`, after successful reconnect and watcher setup, call `_reconcile_from_live_state()`
- [ ] In `on_eink_toggled()`, after successful `switch_to_eink(...)`, call `_reconcile_from_live_state()`
- [ ] In `_on_window_activated()`, replace direct touch-policy ownership with a reconcile request after debounce
- [ ] Ensure trigger paths do not duplicate touch/inhibitor/orientation policy outside `_reconcile_from_live_state()`
- [ ] Preserve existing error handling and `check_ec_status` scheduling
- [ ] Run `python3 -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Verify the new trigger-orchestration tests pass

**Notes:**
- A trigger may still do trigger-local bookkeeping like debounce.
- A trigger should not decide whether touch or inhibitor work is needed.

### Task 3: Simplify and document the reconciler as the single policy owner
- [ ] Modify `Tinta4Plus.py`
- [ ] Add the explanatory comment block above `_reconcile_from_live_state()` describing the reconciler policy
- [ ] Review `_reconcile_from_live_state()` and keep policy decisions centralized there:
  - [ ] read live display mode
  - [ ] read live lid state
  - [ ] ensure inhibitor state matches live mode
  - [ ] ensure E-Ink rotation matches lid state when in E-Ink mode
  - [ ] ensure touch recovery/remap happens only from reconciler-owned E-Ink decisions
  - [ ] update remembered `_live_sync_state`
  - [ ] sync UI from live state
- [ ] Keep reconciler idempotent: no duplicate inhibitor spawns, no unnecessary rotation, no unnecessary touch work
- [ ] Run `python3 -m unittest tests.test_tinta4plus_ui_state -v`
- [ ] Verify existing reconciler lifecycle/orientation tests still pass

**Notes:**
- Do not introduce a second policy function unless the existing reconciler becomes impossible to reason about.
- Prefer reducing branches over adding new special-case helpers.

### Task 4: Strengthen regression tests around the state machine
- [ ] Modify `tests/test_tinta4plus_ui_state.py` only if needed for coverage gaps
- [ ] Ensure tests cover:
  - [ ] no duplicate inhibitor process creation
  - [ ] lid-driven E-Ink rotation remains correct
  - [ ] duplicate invalidations with no effective state change stay cheap
  - [ ] window activation debounce still works
  - [ ] non-E-Ink modes do not perform E-Ink-only side effects
- [ ] Add brief test comments where intent is non-obvious, especially around “trigger vs policy owner” expectations
- [ ] Run:
```bash
python3 -m unittest \
  tests.test_tinta4plus_ui_state \
  tests.test_mode_switch_input_mode \
  tests.test_mode_switch_state \
  -v
```
- [ ] Verify PASS with no new failures

### Task 5: Final verification and review of simplification
- [ ] Inspect the final diff:
```bash
git diff -- Tinta4Plus.py tests/test_tinta4plus_ui_state.py docs/plans/2026-04-05-eink-live-state-reconcile.md
```
- [ ] Confirm policy is simpler than before:
  - [ ] triggers only request reconcile
  - [ ] reconciler owns E-Ink usability policy
  - [ ] comments explain why
  - [ ] tests lock the state-machine shape
- [ ] If the diff still shows trigger-specific policy branching, simplify before finishing
