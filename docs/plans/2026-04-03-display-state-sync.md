# Display State Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make GUI and CLI derive current display mode from shared state detection so startup, reconnect, timers, controls, and exit behavior match the real OLED/E-Ink state.

**Architecture:** Add a shared display-state probe in `mode_switch.py` that reports `oled`, `eink`, `mixed`, or `unknown` based on `DisplayManager.is_display_active(...)`. Update both the CLI and Tk GUI to consume that shared state. Keep presentation logic in `Tinta4Plus.py`, including widget enablement, timers, floating button lifecycle, and frontlight warning/slider state.

**Tech Stack:** Python 3, tkinter, unittest, existing `DisplayManager`, `HelperClient`, and shared `mode_switch.py` utilities.

---

## Rules for execution

- [ ] Follow TDD for every task: write the failing test first, run it, implement the minimum fix, rerun the test.
- [ ] **Commit after each task before moving to the next one.** Do not batch multiple tasks into one commit.
- [ ] If a task uncovers unexpected behavior, update this checklist before continuing.

---

## Task 1: Add shared display-state detection

**Files:**
- Create: `tests/test_mode_switch_state.py`
- Modify: `mode_switch.py`

### Checklist
- [ ] Write failing tests in `tests/test_mode_switch_state.py` for:
  - only `eDP-2` active -> `mode == "eink"`
  - only `eDP-1` active -> `mode == "oled"`
  - both active -> `mode == "mixed"`
  - neither active -> `mode == "unknown"`
- [ ] Run `python -m unittest tests.test_mode_switch_state -v` and confirm it fails because `get_display_state` does not exist yet.
- [ ] Implement `get_display_state(display_mgr)` in `mode_switch.py` returning:
  - `oled_active`
  - `eink_active`
  - `mode`
- [ ] Run `python -m unittest tests.test_mode_switch_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add tests/test_mode_switch_state.py mode_switch.py
  git commit -m "feat: add shared display state detection"
  ```

---

## Task 2: Switch the CLI to shared display-state detection

**Files:**
- Modify: `toggle-eink.py`
- Modify: `tests/test_mode_switch_state.py`

### Checklist
- [ ] Extend `tests/test_mode_switch_state.py` with a CLI-oriented test proving the CLI uses shared state rather than direct `is_display_active(DISPLAY_EINK)` checks.
- [ ] Run `python -m unittest tests.test_mode_switch_state -v` and confirm the new test fails.
- [ ] Update `toggle-eink.py` to import and use `get_display_state` from `mode_switch.py`.
- [ ] Make the CLI choose `switch_to_oled(...)` when `state["mode"] == "eink"` and `switch_to_eink(...)` otherwise.
- [ ] Run `python -m unittest tests.test_mode_switch_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add toggle-eink.py tests/test_mode_switch_state.py
  git commit -m "refactor: use shared display state detection in cli"
  ```

---

## Task 3: Add GUI display-state sync behavior

**Files:**
- Create: `tests/test_tinta4plus_ui_state.py`
- Modify: `Tinta4Plus.py`

### Checklist
- [ ] Write failing GUI sync tests in `tests/test_tinta4plus_ui_state.py` without creating a real Tk window.
- [ ] Cover at least:
  - eInk active -> button says enabled, refresh/mode buttons enabled, timer started, floating button ensured
  - OLED active -> button says disabled, refresh/mode buttons disabled, timer stopped, floating button destroyed
  - mixed or unknown -> conservative disabled UI with a warning/log
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it fails because the sync helpers do not exist yet.
- [ ] Add `_ensure_floating_refresh_button(self)` to `Tinta4Plus.py`.
- [ ] Add `_destroy_floating_refresh_button(self)` to `Tinta4Plus.py`.
- [ ] Add `sync_ui_from_display_state(self)` to `Tinta4Plus.py` using shared `get_display_state(...)`.
- [ ] Keep UI ownership in `Tinta4Plus.py`:
  - widget text/color
  - button enable/disable state
  - periodic refresh timer lifecycle
  - floating refresh button lifecycle
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "feat: sync gui widgets from shared display state"
  ```

---

## Task 4: Sync GUI state on startup, reconnect, and successful toggles

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests proving `initialize_helper()` calls `sync_ui_from_display_state()` after a successful helper connect.
- [ ] Add failing tests proving `attempt_helper_restart()` calls `sync_ui_from_display_state()` after a successful reconnect.
- [ ] Add failing tests proving successful `on_eink_toggled()` paths reuse `sync_ui_from_display_state()` instead of manually duplicating widget state changes.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm the lifecycle tests fail.
- [ ] Update `initialize_helper()` to call `self.sync_ui_from_display_state()` immediately after a successful helper connection.
- [ ] Update `attempt_helper_restart()` to call `self.sync_ui_from_display_state()` immediately after a successful reconnect.
- [ ] Update successful toggle paths to use `self.sync_ui_from_display_state()`.
- [ ] Keep user-facing status messages, but remove duplicated widget-state mutation where the sync method now owns it.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "refactor: sync gui state on connect reconnect and toggle"
  ```

---

## Task 5: Fix frontlight recovery UI state

**Files:**
- Modify: `Tinta4Plus.py`
- Modify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Add failing tests for `check_ec_status()` covering:
  - EC available + Secure Boot off -> brightness slider enabled, warning hidden, frontlight state synced
  - EC unavailable or Secure Boot on -> brightness slider disabled, warning shown
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it fails in the recovery path.
- [ ] Update `check_ec_status()` so the success path explicitly:
  - enables `brightness_scale`
  - hides the `secure_boot_warning`
  - calls `sync_frontlight_state()`
- [ ] Keep the existing disable path for unavailable EC / Secure Boot enabled.
- [ ] Run `python -m unittest tests.test_tinta4plus_ui_state -v` and confirm it passes.
- [ ] Commit progress:
  ```bash
  git add Tinta4Plus.py tests/test_tinta4plus_ui_state.py
  git commit -m "fix: resync frontlight controls after ec recovery"
  ```

---

## Task 6: Final verification

**Files:**
- Verify: `mode_switch.py`
- Verify: `toggle-eink.py`
- Verify: `Tinta4Plus.py`
- Verify: `tests/test_mode_switch_state.py`
- Verify: `tests/test_tinta4plus_ui_state.py`

### Checklist
- [ ] Run the focused automated tests:
  ```bash
  python -m unittest \
    tests.test_mode_switch_state \
    tests.test_tinta4plus_ui_state \
    tests.test_helper_daemon_http \
    tests.test_http_unix_socket_protocol \
    tests.test_unix_socket_protocol -v
  ```
- [ ] Confirm all focused tests pass.
- [ ] Run a quick manual verification:
  ```bash
  ./toggle-eink.py
  python Tinta4Plus.py
  ```
- [ ] Manually verify:
  - start GUI while already on E-Ink -> button shows enabled
  - refresh/mode buttons enabled when E-Ink is active
  - floating refresh button appears when E-Ink is active
  - reconnect resyncs GUI state
  - frontlight slider recovers when EC access is available
  - closing app while synced to E-Ink still follows the OLED/privacy-image path
- [ ] Review the diff:
  ```bash
  git status --short
  git diff -- mode_switch.py toggle-eink.py Tinta4Plus.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
  ```
- [ ] Commit final verification or cleanup if needed:
  ```bash
  git add mode_switch.py toggle-eink.py Tinta4Plus.py tests/test_mode_switch_state.py tests/test_tinta4plus_ui_state.py
  git commit -m "test: verify display state sync across gui and cli"
  ```
