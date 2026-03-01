# Systemd Socket Activation for Tinta4Plus Helper (Design)

**Date:** 2026-03-01  
**Branch:** `taras/fixes`

## Goal
Replace runtime `pkexec` helper launch with a systemd socket-activated root helper so the GUI connects reliably without auth timing races, while keeping a `pkexec` path for one-time installation/bootstrap.

## Current Problem Summary
- GUI currently starts helper via `pkexec` and then waits for `/tmp/tinta4plus.sock`.
- User auth delay and helper startup timing can produce false-negative launch failures.
- Runtime auth prompt is fragile UX and hard to reason about.

## Target Architecture

### Runtime (normal use)
1. GUI connects to `/run/tinta4plus.sock`.
2. `tinta4plus-helper.socket` is active and owns that socket.
3. On first connection, systemd activates `tinta4plus-helper.service` as root.
4. Helper serves requests over the inherited socket (systemd socket activation path).
5. No runtime `pkexec` prompt.

### Bootstrap/install (one-time or upgrade)
1. User runs install command/script.
2. Install uses `pkexec` for privileged steps only.
3. Installer places helper binary and unit files, configures permissions/group, enables socket unit.

## Security Model
- Socket path: `/run/tinta4plus.sock`
- Socket permissions: `0660`
- Socket group: `tinta4plus`
- Access control: only users in `tinta4plus` group can open socket.
- Helper remains root and must validate all command inputs and ranges.
- Optional hardening: peer credential check (`SO_PEERCRED`) to restrict allowed UIDs.

## Proposed File Changes

### New files
- `contrib/systemd/tinta4plus-helper.socket`
- `contrib/systemd/tinta4plus-helper.service`

### Modified files
- `HelperDaemon.py`
  - Add support for inherited systemd socket FD (`LISTEN_FDS` flow).
  - Keep fallback bind/listen behavior for manual/dev mode.
  - is launched directly by unit
- `Tinta4Plus.py`
  - Prefer `/run/tinta4plus.sock`.
  - remove all code with old `/tmp/tinta4plus.sock`  legacy mode.
  - Adjust helper initialization flow to avoid runtime `pkexec` when systemd socket mode is available. eg instead offer to install daemon and user for it add current user to the group..use pkexec for that once user says ye
  - during helper connection, check if the installed service is older than the HelperDaemon.py next to Tinata4Plus.py..then also run  the install workflow via pkexecs
- `README.md`
  - Document installation, group membership, and verification commands.

## Unit Definitions (intent)

### `tinta4plus-helper.socket`
- Listens on Unix socket `/run/tinta4plus.sock`
- `SocketMode=0660`
- `SocketGroup=tinta4plus`
- Activated at boot (`WantedBy=sockets.target`)

### `tinta4plus-helper.service`
- Runs helper as root
- Started by socket activation (no need for manual start)
- Uses installed helper path (e.g., `/usr/local/bin/HelperDaemon.py`)
- Restart policy conservative (e.g., `Restart=on-failure`)

## Installer Responsibilities

### User entrypoint (`install-systemd-helper.sh`)
- Presents friendly output for success/failure and post-install steps.

### Root installer (`install-systemd-helper-root.sh`)
- Ensure `tinta4plus` group exists.
- Add invoking user to `tinta4plus` group (if desired and safe).
- Install helper to `/usr/local/bin/HelperDaemon.py` with executable perms.
- Install unit files into `/etc/systemd/system/`.
- `systemctl daemon-reload`
- `systemctl enable --now tinta4plus-helper.socket`
- restart unit in case it was installed before

## Migration / Compatibility Strategy
- No legacy path.
- Remove all manual/debug-mode artifacts and assumptions:
  - remove `shutdown` command usage from GUI/client disconnect flow
  - remove helper protocol `shutdown` command handler
  - remove fallback/manual socket bind mode in helper (systemd socket activation only)
  - remove any `/tmp/tinta4plus.sock` references
  - remove any runtime `pkexec` helper-launch logic (install/update only)

## Verification Plan
1. Install via new installer script.
2. Confirm socket unit active:
   - `systemctl status tinta4plus-helper.socket`
3. Confirm socket exists with correct mode/group:
   - `ls -l /run/tinta4plus.sock`
4. Launch GUI and ASK USER TO verify no runtime auth prompt.
5. Confirm helper starts on first connection:
   - `systemctl status tinta4plus-helper.service`
6. Exercise key commands (enable/disable/refresh/frontlight).
7. Confirm reconnection behavior after helper restart.

## Risks and Mitigations
- **Group membership not applied until new login**
  - Mitigation: document re-login/newgrp requirement.
- **Permission misconfiguration on `/run` socket**
  - Mitigation: explicit unit settings + install-time checks.

## Execution Order
0. Undo prior pkexec startup-hardening patch first (restore baseline before systemd migration).
1. Add units + installer.
2. Add helper socket-activation support.
3. Switch GUI to `/run/tinta4plus.sock` and remove runtime pkexec launch path.
4. Validate end-to-end.