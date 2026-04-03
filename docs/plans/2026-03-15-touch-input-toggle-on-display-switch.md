# Touch Input Toggle on Display Switch (TL;DR Plan)

Goal: make touch/pen device toggling happen in the shared switch path so GUI and CLI behave the same.

## Scope
- Modify only: `mode_switch.py`

## Plan
1. Add small `xinput` helpers:
   - list devices from `xinput --list --short`
   - match IDs by name patterns
   - enable/disable IDs

2. Use device name groups:
   - E-Ink input group: `ITE Tech. Inc. ITE T-CON*`
   - OLED input group: `Wacom HID 537D*`

3. Add `_apply_input_mode(target)`:
   - `target="eink"`: enable E-Ink IDs, disable OLED IDs
   - `target="oled"`: enable OLED IDs, disable E-Ink IDs

4. Hook into shared switch path:
   - in `switch_to_eink(...)` call `_apply_input_mode("eink")`
   - in `switch_to_oled(...)` call `_apply_input_mode("oled")`

5. Failure policy:
   - input toggling errors are warning-only
   - do not fail display switching if `xinput` step fails

6. Manual verification:
   - run `./toggle-eink.py` in both directions
   - check monitor: `xrandr --listmonitors`
   - check input states:
     - `xinput list-props <id> | grep "Device Enabled"`

## Expected result
- On E-Ink mode: ITE devices enabled, Wacom devices disabled.
- On OLED mode: Wacom devices enabled, ITE devices disabled.
