# Touch Input Logging Design

**Goal:** Add INFO-level logging around touch/input X11 command execution so future rotation and display-switch failures can be diagnosed from logs without manual `xinput` inspection.

## Problem

Current touch/input handling in `mode_switch.py` has only coarse logging:
- high-level switch/rotation flows log success or warning outcomes
- `_run_xinput(...)` only logs failures
- successful `xinput` commands, matched device IDs, and chosen outputs are not logged

That makes it hard to tell after the fact:
- whether input remap actually ran
- which devices were matched for OLED vs E-Ink
- which IDs were enabled/disabled/mapped
- which exact command failed

## Requirements

- Log touch-related `xinput` commands at **INFO** level during normal runs.
- Keep behavior unchanged; this is diagnostics only.
- Log enough context to diagnose future failures without reproducing manually.
- Keep failure logging detailed and structured.
- Add test coverage for the new logging behavior.

## Approach Options

### Option A: Log only inside `_run_xinput(...)`
Pros:
- Smallest code change
- Central place for command execution

Cons:
- Does not explain why a command ran
- Does not log device matching or target mode decisions

### Option B: Log both command execution and input-mode decisions (**recommended**)
Pros:
- Gives both low-level and high-level context
- Lets us correlate target mode, matched devices, and exact commands
- Minimal behavior risk

Cons:
- Slightly noisier logs

### Option C: Add separate debug dump helper
Pros:
- More structured snapshots

Cons:
- More code
- More than needed for the current diagnostic need

## Recommended Design

Implement Option B.

### Command-level logging
In `mode_switch.py`:
- `_run_xinput(logger, args)` logs the exact command before execution
- on success, log command success and trimmed stdout if present
- on failure, log command, return code details, and stderr/stdout if present

### Decision-level logging
In `_apply_input_mode(logger, target)`:
- log matched E-Ink and OLED devices by ID and name
- log selected target output
- log the enable/disable sets
- log final success/failure summary

### Non-goals
- No touch behavior changes
- No rotation math changes
- No CTM/Wacom-specific fixes yet

## Testing

Extend `tests/test_mode_switch_input_mode.py` to cover:
- `_run_xinput(...)` logs before and after successful command execution
- `_run_xinput(...)` logs detailed failure information
- `_apply_input_mode(...)` logs mode decisions and final summary

## Files

- Modify: `mode_switch.py`
- Modify: `tests/test_mode_switch_input_mode.py`
