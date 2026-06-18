# Orientation Toggle Design

**Goal:** Add a UI control that toggles the active internal display between landscape and portrait, syncs from live `xrandr` state on startup, and keeps later OLED↔E-Ink switches aligned with the last orientation chosen in the app.

## Requirements

- Add a button in the GUI display controls for orientation.
- Use user-facing labels `Landscape` and `Portrait`.
- Map the two supported modes to:
  - `Landscape` -> `xrandr --rotate normal`
  - `Portrait` -> `xrandr --rotate left`
- Only one internal output is active at a time; operate on the active output only.
- On startup, do **not** force rotation. Read current state from `xrandr` and sync the UI to reality.
- After the user changes orientation in the app, later OLED↔E-Ink switches should apply that last app-selected orientation to the newly active output.
- Keep failures non-fatal and visible through logging/UI status.

## Recommended Approach

Introduce shared rotation helpers in `DisplayManager.py`, keep mode-switch ownership in `mode_switch.py`, and keep button/state presentation in `Tinta4Plus.py`.

This separates concerns cleanly:
- `DisplayManager.py` owns `xrandr` querying and rotation commands.
- `mode_switch.py` owns when rotation is re-applied after shared OLED/E-Ink switching.
- `Tinta4Plus.py` owns labels, button state, startup sync, and click handling.

## Behavior

### Startup
- Detect the active display (`eDP-1` or `eDP-2`).
- Query its current rotation from `xrandr`.
- Update the GUI button to show `Orientation: Landscape` or `Orientation: Portrait`.
- Do not change display rotation during startup sync.

### Button press
- Toggle the target rotation for the active display.
- Apply rotation via `xrandr --output <display> --rotate <normal|left>`.
- Re-read `xrandr` to confirm the resulting state.
- Update the UI only after confirmation.
- Save the last app-selected orientation so future display switches can reuse it.

### Display switching
- After `switch_to_eink(...)` or `switch_to_oled(...)` successfully enables the target display, apply the last app-selected orientation if one exists.
- Re-apply input mapping afterward if needed so touch/stylus stays aligned.
- If no app-selected orientation has been stored yet, do not impose one.

## Edge Cases

- If no active display is detected, disable the orientation button and log a warning.
- If `xrandr` rotation fails, leave the UI showing the last confirmed live state.
- If the user changes rotation outside the app, the next startup sync reflects that live state.
- Because E-Ink refresh is slower, status text/logging should make rotation activity explicit.

## Files

- Modify: `DisplayManager.py`
- Modify: `mode_switch.py`
- Modify: `Tinta4Plus.py`
- Modify: `toggle-eink.py` only if settings loading or shared helpers need a small extension
- Add/modify tests in:
  - `tests/test_display_manager_rotation.py`
  - `tests/test_mode_switch_rotation.py`
  - `tests/test_tinta4plus_ui_state.py`

## Testing

- Unit-test `xrandr` parsing and rotation command generation.
- Unit-test shared mode-switch rotation re-application behavior.
- Unit-test GUI startup sync and button toggle behavior without creating a real Tk window.
- Manually verify on hardware:
  - startup sync reflects current `xrandr` orientation
  - button toggles active display between landscape/portrait
  - switching OLED↔E-Ink preserves the last app-selected orientation
  - touch/input remains mapped correctly after rotation
