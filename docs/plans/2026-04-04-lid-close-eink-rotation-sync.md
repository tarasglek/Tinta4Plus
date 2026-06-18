# Lid-Close E-Ink Rotation Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the GUI stay synchronized with out-of-band display changes, hold a lid-close suspend inhibitor while E-Ink is active, and rotate E-Ink to portrait on lid close and back to landscape on lid open with touch remap/recovery after each rotation.

**Architecture:** Keep `Tinta4Plus.py` as the sole policy owner and UI owner. Add one small Python helper process that blocks on lid and RandR/display-change events and sends only invalidation notifications to the parent over a single IPC channel. The parent re-reads live lid/display state on every event and runs one Tk-thread reconciliation method that decides whether E-Ink is active, whether the inhibitor must run, and whether to rotate/remap/recover touch.

**Tech Stack:** Python 3, tkinter, multiprocessing (`Process`, `Pipe`), X11 RandR notifications, D-Bus login1 lid notifications, `systemd-inhibit`, existing `DisplayManager.py` / `mode_switch.py` rotation and touch helpers, unittest.

---

## Rules for execution

- [ ] Follow TDD for every task: write the failing test first, run it, implement the minimum fix, rerun the test.
- [ ] **Commit after each task before moving to the next one.**
- [ ] `Tinta4Plus.py` remains the only owner of policy and side effects.
- [ ] The helper process emits invalidations only; it must not decide lid policy, display mode, rotation, input remap, or inhibitor behavior.
- [ ] All GUI mutation stays on the Tk thread.
- [ ] On every helper event, the parent must treat live system state as the source of truth.

---

## Task 1: Add one GUI reconciler for live lid/display state

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests for a small GUI-owned state model tracking:
  - display mode
  - lid state
  - inhibitor running/not running
  - last applied E-Ink orientation
- [ ] Add a failing test for one parent-owned method such as `_reconcile_from_live_state()`.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement the minimal GUI-owned sync state and reconciler entry point in `Tinta4Plus.py`.
- [ ] Ensure the reconciler reads live display state and live lid state itself.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: add gui reconciler for lid and display state"
  ```

---

## Task 2: Add one helper process for lid and RandR invalidations

**Files:**
- Modify: `Tinta4Plus.py`
- Create: `event_watcher.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests proving one helper process is started and stopped cleanly.
- [ ] Add a failing test proving one IPC channel is used.
- [ ] Add failing tests for helper notifications:
  - `("lid", None)`
  - `("randr", None)`
  - `("error", "...")`
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement `event_watcher.py` as one helper process watching both lid and RandR events.
- [ ] Use one `multiprocessing.Pipe` between GUI and helper.
- [ ] Keep helper output limited to invalidations only.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py event_watcher.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: add single helper for lid and randr invalidations"
  ```

---

## Task 3: Connect helper notifications to Tk-thread reconciliation

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests proving helper notifications trigger reconciliation on the Tk thread.
- [ ] Add a failing test proving the notification path does not perform direct side effects.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement the minimal parent receive path for helper notifications.
- [ ] Ensure helper notifications only schedule or trigger `_reconcile_from_live_state()`.
- [ ] Log helper errors without crashing the GUI.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: trigger reconciliation from helper events"
  ```

---

## Task 4: Add inhibitor lifecycle in the reconciler

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests proving the reconciler starts `systemd-inhibit` when display mode becomes `eink`.
- [ ] Add failing tests proving the reconciler stops it when display mode is not `eink`.
- [ ] Add a failing test proving duplicate events do not create duplicate inhibitors.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement minimal inhibitor lifecycle helpers in `Tinta4Plus.py`.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: hold lid-close inhibitor while eink is active"
  ```

---

## Task 5: Add lid-driven E-Ink rotation and touch recovery

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`
- Verify: `mode_switch.py`

### Checklist
- [ ] Add failing tests proving:
  - `eink + lid closed -> portrait`
  - `eink + lid open -> landscape`
  - `not eink -> no lid-driven orientation action`
- [ ] Add failing tests proving orientation changes apply the correct rotation, reapply E-Ink input mode, and call `ensure_touch_available(self.logger, "eink")`.
- [ ] Add a failing test proving duplicate invalidations with no effective change are ignored.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement minimal desired-orientation logic and action path in the reconciler.
- [ ] Keep the reconciler idempotent.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: rotate and recover touch from lid-driven eink state"
  ```

---

## Task 6: Handle out-of-band display changes and shutdown cleanup

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `event_watcher.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests proving a `randr` invalidation causes GUI resync from live state.
- [ ] Add failing tests proving app shutdown stops helper handling, stops the helper process, and stops the inhibitor.
- [ ] Add a failing test proving helper `error` notifications are logged and do not crash the GUI.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm failure.
- [ ] Implement minimal resync and cleanup behavior.
- [ ] Do not add restart machinery unless required by observed failures.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm pass.
- [ ] Commit:
  ```bash
  git add Tinta4Plus.py event_watcher.py tests/test_tinta4plus_ui_state.py
  git commit -m "fix: resync gui and clean up helper lifecycle"
  ```

---

## Task 7: Final verification

**Files:**
- Verify: `Tinta4Plus.py`
- Verify: `event_watcher.py`
- Verify: `mode_switch.py`
- Verify: `DisplayManager.py`
- Verify: `tests/test_tinta4plus_ui_state.py`
- Verify: `tests/test_mode_switch_rotation.py`
- Verify: `tests/test_mode_switch_input_mode.py`

### Checklist
- [ ] Run focused automated tests:
  ```bash
  python -m unittest \
    tests.test_tinta4plus_ui_state \
    tests.test_mode_switch_rotation \
    tests.test_mode_switch_input_mode -v
  ```
- [ ] Run the broader suite:
  ```bash
  python -m unittest discover -s tests -v
  ```
- [ ] Run manual hardware verification:
  ```bash
  python Tinta4Plus.py
  ```
- [ ] Manually verify:
  - switching to E-Ink starts the inhibitor
  - switching away from E-Ink stops the inhibitor
  - out-of-band display changes resync the GUI
  - lid close while E-Ink is active rotates to portrait
  - lid open while E-Ink is active rotates back to landscape
  - touch remains usable after both lid-driven rotations
  - lid events while OLED is active do not force E-Ink behavior
- [ ] Inspect inhibitors:
  ```bash
  systemd-inhibit --list
  ```
- [ ] Inspect the diff:
  ```bash
  git status --short
  git diff -- Tinta4Plus.py event_watcher.py mode_switch.py DisplayManager.py tests/test_tinta4plus_ui_state.py tests/test_mode_switch_rotation.py tests/test_mode_switch_input_mode.py
  ```
- [ ] Commit final cleanup if needed:
  ```bash
  git add Tinta4Plus.py event_watcher.py mode_switch.py DisplayManager.py tests/test_tinta4plus_ui_state.py tests/test_mode_switch_rotation.py tests/test_mode_switch_input_mode.py
  git commit -m "feat: sync eink lid rotation with helper-driven lid and randr events"
  ```
