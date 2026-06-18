# Display Power Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve OLED display power-management settings, disable all display blanking while on E-Ink, and restore OLED settings when switching back.
**Architecture:** Replace the narrow DPMS snapshot with a broader display power policy snapshot covering xset screensaver/DPMS and XFCE power-manager keys. Keep existing switch call sites so GUI/CLI behavior remains unchanged.
**Tech Stack:** Python, unittest, subprocess-backed X11/XFCE commands.

---

- [x] Task 1: Add xset screensaver capture/restore tests
  - Files: `tests/test_mode_switch_power_policy.py`, `mode_switch.py`
  - Test first: parse `xset q` output with Screen Saver and DPMS sections.
  - Verify RED: `python3 -m unittest tests.test_mode_switch_power_policy` should fail because helpers do not exist / screensaver is not captured.
  - Implement: capture `screensaver_timeout`, `screensaver_cycle`, DPMS enabled/timeouts in a unified state.
  - Verify GREEN: `python3 -m unittest tests.test_mode_switch_power_policy`

- [x] Task 2: Add XFCE power-manager snapshot/apply/restore tests
  - Files: `tests/test_mode_switch_power_policy.py`, `mode_switch.py`
  - Test first: fake `xfconf-query` get/set calls for blanking and DPMS keys.
  - Verify RED: command expectations fail because XFCE state is not handled.
  - Implement: query configured XFCE keys, save present values with type metadata, set E-Ink policy values, restore saved values.
  - Verify GREEN: `python3 -m unittest tests.test_mode_switch_power_policy`

- [x] Task 3: Integrate with existing mode switching and compatibility
  - Files: `mode_switch.py`, existing tests
  - Test first: ensure existing `_disable_dpms_for_eink` and `_restore_dpms_after_eink` use the broader policy and do not overwrite an existing snapshot.
  - Verify RED: focused unittest should fail under old behavior.
  - Implement: keep function names as compatibility wrappers; add legacy `dpms_saved_state` restore fallback.
  - Verify GREEN: `python3 -m unittest tests.test_mode_switch_power_policy tests.test_mode_switch_rotation tests.test_mode_switch_state`

- [x] Task 4: Full verification and commit
  - Files: all touched files only.
  - Verify: `python3 -m unittest discover tests`
  - Review: `git diff -- mode_switch.py tests/test_mode_switch_power_policy.py docs/plans/2026-06-18-display-power-policy.md`
  - Commit: stage only intended files and commit with Conventional Commit subject.
