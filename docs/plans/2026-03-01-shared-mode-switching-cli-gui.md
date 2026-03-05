# Shared mode switching for GUI + CLI (minimal plan)

1. **Create shared module** (`mode_switch.py`)
   - Move mode transitions there:
     - switch to E-Ink
     - switch to OLED
   - Include:
     - privacy image before E-Ink off
     - XFCE theme switch (HighContrast/Adwaita-dark)

2. **Use it from GUI**
   - Replace transition logic in `Tinta4Plus.py` with calls to `mode_switch.py`
   - Keep GUI-only behavior (buttons/timers/dialogs) in GUI file

3. **Use it from CLI**
   - Make `toggle-eink.py` call the same shared functions
   - Keep CLI no-options, just toggle

4. **Quick manual check**
   - Toggle twice with CLI and confirm:
     - E-Ink path works
     - OLED path shows privacy image + theme changes

5. **Config parity**
   - Read `~/.config/Tinta4Plus/settings`
   - Use `autoswitch_theme` and `display_scale` in CLI same as GUI
   - Keep defaults if missing:
     - `autoswitch_theme=True`
     - `display_scale=1.75`
