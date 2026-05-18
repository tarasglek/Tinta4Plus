# Disable E-Ink Output User Unit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install and update a systemd user unit that runs `xrandr` at login to disable the E-Ink X11 output and keep OLED primary.
**Architecture:** Add a repo-tracked user unit and let the GUI install/check it in the current user's systemd user config. Keep privileged helper installation unchanged.
**Tech Stack:** Python/Tkinter GUI, systemd --user, xrandr, shell subprocesses.

---

- [ ] Task 1: Add tracked user unit
  - Files: `contrib/systemd/user/tinta4plus-disable-eink-output.service`
  - Change: Create a oneshot unit with an `ExecStart=/usr/bin/xrandr --output eDP-2 --off --output eDP-1 --auto --primary` and a comment explaining X11 `DISPLAY`/`XAUTHORITY` requirements.
  - Verify: `systemd-analyze --user verify contrib/systemd/user/tinta4plus-disable-eink-output.service`

- [ ] Task 2: Extend GUI drift check
  - Files: `Tinta4Plus.py`
  - Test first: add/modify a unit test if existing install-check tests exist; otherwise manually verify with `python3 -m py_compile Tinta4Plus.py`.
  - Implement: Add helpers to compare the repo user unit with `~/.config/systemd/user/tinta4plus-disable-eink-output.service` and check `systemctl --user is-enabled tinta4plus-disable-eink-output.service`.
  - Verify: `python3 -m py_compile Tinta4Plus.py`

- [ ] Task 3: Install/enable user unit with --now
  - Files: `Tinta4Plus.py`
  - Implement: After successful root helper install, copy the user unit to `~/.config/systemd/user/`, run `systemctl --user daemon-reload`, then `systemctl --user enable --now tinta4plus-disable-eink-output.service`.
  - Verify: `python3 -m py_compile Tinta4Plus.py`
  - Manual check: `systemctl --user status tinta4plus-disable-eink-output.service --no-pager`

- [ ] Task 4: End-to-end verification
  - Run: `python3 -m pytest tests` if pytest is available.
  - Run: GUI installer flow or helper methods manually if GUI automation is impractical.
  - Check: user unit is enabled and current display layout has `eDP-2` off after the `--now` start.
