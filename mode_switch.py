#!/usr/bin/env python3
"""Shared OLED <-> E-Ink mode switching logic for GUI and CLI."""

import fnmatch
import json
import os
import re
import subprocess
import time

DISPLAY_OLED = "eDP-1"
DISPLAY_EINK = "eDP-2"
THEME_HIGH_CONTRAST = "HighContrast"
THEME_ADWAITA_DARK = "Adwaita-dark"
EINK_DISABLED_IMAGE = "eink-disable.jpg"
CONFIG_DIR = os.path.expanduser("~/.config/Tinta4Plus")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings")
DEFAULT_DPMS_STANDBY = 120
DEFAULT_DPMS_SUSPEND = 0
DEFAULT_DPMS_OFF = 600
EINK_INPUT_PATTERNS = ["ITE Tech. Inc. ITE T-CON*"]
OLED_INPUT_PATTERNS = ["Wacom HID 537D*"]
SUPPORTED_ORIENTATION_ROTATIONS = {"normal", "left"}
ORIENTATION_PREFERENCE_KEY = "orientation_preference"


def get_display_state(display_mgr):
    oled_active = display_mgr.is_display_active(DISPLAY_OLED)
    eink_active = display_mgr.is_display_active(DISPLAY_EINK)

    if oled_active and eink_active:
        mode = "mixed"
    elif oled_active:
        mode = "oled"
    elif eink_active:
        mode = "eink"
    else:
        mode = "unknown"

    return {
        "oled_active": oled_active,
        "eink_active": eink_active,
        "mode": mode,
    }


def helper_command(helper, logger, command, **params):
    try:
        response = helper.send_command(command, **params)
    except Exception as e:
        logger.error(f"{command} exception: {e}")
        return False

    if not response or not response.get("success"):
        error = (response or {}).get("error", "unknown error")
        logger.error(f"{command} failed: {error}")
        return False
    return True


def set_xfce_theme(logger, theme_name):
    try:
        subprocess.run([
            "xfconf-query",
            "-c", "xsettings",
            "-p", "/Net/ThemeName",
            "-s", theme_name,
        ], check=True, capture_output=True)
        logger.info(f"Switched to {theme_name} theme")
        return True
    except Exception as e:
        logger.warning(f"Failed to set theme to {theme_name}: {e}")
        return False


def _run_xinput(logger, args):
    command = f"xinput {' '.join(args)}"
    logger.info(f"Running {command}")

    try:
        result = subprocess.run(["xinput", *args], check=True, capture_output=True, text=True)
        stdout = (result.stdout or "").strip()
        if stdout:
            logger.info(f"{command} succeeded: {stdout}")
        else:
            logger.info(f"{command} succeeded")
        return result.stdout
    except subprocess.CalledProcessError as e:
        details = []
        stderr = (e.stderr or "").strip()
        stdout = (e.output or getattr(e, "stdout", "") or "").strip()
        if stderr:
            details.append(f"stderr={stderr}")
        if stdout:
            details.append(f"stdout={stdout}")
        detail_suffix = f": {'; '.join(details)}" if details else ""
        logger.warning(f"{command} failed (rc={e.returncode}){detail_suffix}")
        return None
    except Exception as e:
        logger.warning(f"{command} failed: {e}")
        return None


def _log_post_switch_display_snapshot(logger, reason):
    """Log concise xrandr state after a display mode switch."""
    try:
        query = subprocess.run(["xrandr", "--query"], check=True, capture_output=True, text=True)
        lines = (query.stdout or "").splitlines()

        screen_line = next((line.strip() for line in lines if line.startswith("Screen ")), "<missing>")
        active_outputs = []
        for line in lines:
            if " connected" not in line:
                continue
            if re.search(r"\b\d+x\d+\+\d+\+\d+\b", line):
                active_outputs.append(line.strip())

        outputs_summary = " | ".join(active_outputs) if active_outputs else "<none>"
        logger.info(f"Display snapshot ({reason}): {screen_line}")
        logger.info(f"Display snapshot ({reason}) active outputs: {outputs_summary}")
    except Exception as e:
        logger.warning(f"Display snapshot ({reason}) xrandr --query failed: {e}")
        return

    try:
        monitors = subprocess.run(["xrandr", "--listactivemonitors"], check=True, capture_output=True, text=True)
        monitor_lines = [line.strip() for line in (monitors.stdout or "").splitlines() if line.strip()]
        logger.info(f"Display snapshot ({reason}) monitors: {' || '.join(monitor_lines)}")
    except Exception as e:
        logger.warning(f"Display snapshot ({reason}) xrandr --listactivemonitors failed: {e}")


def _list_xinput_devices(logger):
    output = _run_xinput(logger, ["--list", "--short"])
    if output is None:
        return []

    devices = []
    for line in output.splitlines():
        if "id=" not in line:
            continue

        name_part, id_part = line.split("id=", 1)
        device_id = id_part.split()[0]
        if not device_id.isdigit():
            continue

        device_name = re.sub(r"^[^0-9A-Za-z]+", "", name_part).strip()
        devices.append({"id": int(device_id), "name": device_name})

    return devices


def _find_matching_input_ids(devices, patterns):
    return [
        device["id"]
        for device in devices
        if any(fnmatch.fnmatch(device["name"], pattern) for pattern in patterns)
    ]


def _set_input_enabled(logger, device_id, enabled):
    action = "enable" if enabled else "disable"
    return _run_xinput(logger, [action, str(device_id)]) is not None


def _map_input_to_output(logger, device_id, output_name):
    return _run_xinput(logger, ["map-to-output", str(device_id), output_name]) is not None


def _expected_touch_ids_for_target(devices, target):
    if target == "eink":
        patterns = EINK_INPUT_PATTERNS
    elif target == "oled":
        patterns = OLED_INPUT_PATTERNS
    else:
        return []

    return sorted(_find_matching_input_ids(devices, patterns))


def _get_device_enabled_state(logger, device_id):
    output = _run_xinput(logger, ["list-props", str(device_id)])
    if output is None:
        return None

    match = re.search(r"Device Enabled \([^)]*\):\s*(\d+)", output)
    if not match:
        return None

    return int(match.group(1))


def _is_touch_healthy_for_target(logger, target):
    devices = _list_xinput_devices(logger)
    if not devices:
        return False

    expected_ids = _expected_touch_ids_for_target(devices, target)
    if not expected_ids:
        return False

    for device_id in expected_ids:
        if _get_device_enabled_state(logger, device_id) == 1:
            return True
    return False


def ensure_touch_available(logger, target):
    if _is_touch_healthy_for_target(logger, target):
        return True

    logger.warning(f"Touch unavailable for {target}; retrying input remap")
    _apply_input_mode(logger, target)

    if _is_touch_healthy_for_target(logger, target):
        logger.info(f"Touch recovered for {target} after input remap retry")
        return True

    logger.warning(f"Touch still unavailable for {target} after input remap retry")
    return False


def reconcile_touch(logger, display_mgr, target=None, reason="unspecified"):
    resolved_target = target

    if resolved_target is None:
        mode = get_display_state(display_mgr).get("mode")
        if mode in ("eink", "oled"):
            resolved_target = mode
        else:
            logger.info(f"Touch reconcile skipped (reason={reason}, mode={mode})")
            return False

    if resolved_target not in ("eink", "oled"):
        logger.warning(f"Touch reconcile skipped (reason={reason}, invalid_target={resolved_target})")
        return False

    recovered = ensure_touch_available(logger, resolved_target)
    if recovered:
        logger.info(f"Touch reconcile succeeded (reason={reason}, target={resolved_target})")
        return True

    logger.warning(f"Touch reconcile failed (reason={reason}, target={resolved_target})")
    return False


def _apply_input_mode(logger, target):
    devices = _list_xinput_devices(logger)
    if not devices:
        logger.warning("No xinput devices found; skipping input mode update")
        return False

    eink_matches = [
        device for device in devices
        if any(fnmatch.fnmatch(device["name"], pattern) for pattern in EINK_INPUT_PATTERNS)
    ]
    oled_matches = [
        device for device in devices
        if any(fnmatch.fnmatch(device["name"], pattern) for pattern in OLED_INPUT_PATTERNS)
    ]
    eink_ids = {device["id"] for device in eink_matches}
    oled_ids = {device["id"] for device in oled_matches}

    logger.info(
        f"Input mode {target}: matched E-Ink devices {sorted(eink_ids)}, OLED devices {sorted(oled_ids)}"
    )

    if target == "eink":
        enable_ids = sorted(eink_ids)
        disable_ids = sorted(oled_ids - eink_ids)
        target_output = DISPLAY_EINK
    elif target == "oled":
        enable_ids = sorted(oled_ids)
        disable_ids = sorted(eink_ids - oled_ids)
        target_output = DISPLAY_OLED
    else:
        logger.warning(f"Unknown input mode target: {target}")
        return False

    logger.info(
        f"Input mode {target}: target_output={target_output} enable_ids={enable_ids} disable_ids={disable_ids}"
    )

    success = True
    for device_id in enable_ids:
        if not _set_input_enabled(logger, device_id, True):
            success = False
        if not _map_input_to_output(logger, device_id, target_output):
            success = False

    for device_id in disable_ids:
        if not _set_input_enabled(logger, device_id, False):
            success = False

    logger.info(
        f"Input mode {target} applied {'successfully' if success else 'with failures'}"
    )
    return success


def _resolve_privacy_image_path(script_dir):
    image_path = EINK_DISABLED_IMAGE
    if os.path.exists(image_path):
        return image_path

    image_path = os.path.join(script_dir, EINK_DISABLED_IMAGE)
    if os.path.exists(image_path):
        return image_path

    return None


def _load_settings(logger):
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"Could not read settings for DPMS state: {e}")
    return {}


def _save_settings(logger, settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        logger.warning(f"Could not write settings for DPMS state: {e}")
        return False


def load_orientation_preference(logger):
    settings = _load_settings(logger)
    value = settings.get(ORIENTATION_PREFERENCE_KEY)
    if value in SUPPORTED_ORIENTATION_ROTATIONS:
        return value
    if value is not None:
        logger.warning(f"Ignoring unsupported orientation preference '{value}'")
    return None


def save_orientation_preference(logger, rotation):
    if rotation not in SUPPORTED_ORIENTATION_ROTATIONS:
        logger.warning(f"Refusing to save unsupported orientation '{rotation}'")
        return False

    settings = _load_settings(logger)
    settings[ORIENTATION_PREFERENCE_KEY] = rotation
    return _save_settings(logger, settings)


def apply_stored_orientation(display_mgr, logger, target):
    rotation = load_orientation_preference(logger)
    if rotation is None:
        return False

    active_display = display_mgr.get_active_display()
    if not active_display:
        logger.warning("No active display found for orientation re-apply")
        return False

    if not display_mgr.set_display_rotation(active_display, rotation):
        logger.warning(f"Failed to apply stored orientation '{rotation}' on {active_display}")
        return False

    if not _apply_input_mode(logger, target):
        logger.warning(f"Applied orientation on {active_display}, but input remap failed for {target}")

    return True


def _capture_dpms_state(logger):
    try:
        result = subprocess.run(["xset", "q"], check=True, capture_output=True, text=True)
        output = result.stdout
    except Exception as e:
        logger.warning(f"Could not query DPMS state via xset: {e}")
        return None

    enabled = None
    standby = suspend = off = None

    m_enabled = re.search(r"DPMS is\s+(Enabled|Disabled)", output)
    if m_enabled:
        enabled = (m_enabled.group(1) == "Enabled")

    m_timeouts = re.search(r"Standby:\s*(\d+)\s+Suspend:\s*(\d+)\s+Off:\s*(\d+)", output)
    if m_timeouts:
        standby = int(m_timeouts.group(1))
        suspend = int(m_timeouts.group(2))
        off = int(m_timeouts.group(3))

    if enabled is None or standby is None or suspend is None or off is None:
        logger.warning("Could not parse full DPMS state from xset output")
        return None

    return {
        "enabled": enabled,
        "standby": standby,
        "suspend": suspend,
        "off": off,
    }


def _save_dpms_state(logger, dpms_state):
    settings = _load_settings(logger)
    settings["dpms_saved_state"] = dpms_state
    _save_settings(logger, settings)


def _load_dpms_state(logger):
    settings = _load_settings(logger)
    value = settings.get("dpms_saved_state")
    return value if isinstance(value, dict) else None


def _clear_dpms_state(logger):
    settings = _load_settings(logger)
    if "dpms_saved_state" in settings:
        del settings["dpms_saved_state"]
        _save_settings(logger, settings)


def _disable_dpms_for_eink(logger):
    state = _capture_dpms_state(logger)
    if state:
        _save_dpms_state(logger, state)
        logger.info(f"Saved DPMS state: enabled={state['enabled']}, standby={state['standby']}, suspend={state['suspend']}, off={state['off']}")

    try:
        subprocess.run(["xset", "-dpms"], check=True, capture_output=True)
        logger.info("Disabled DPMS for E-Ink mode")
    except Exception as e:
        logger.warning(f"Could not disable DPMS: {e}")


def _restore_dpms_after_eink(logger):
    state = _load_dpms_state(logger)

    if not state:
        current = _capture_dpms_state(logger)
        if current and not current.get("enabled", True):
            try:
                subprocess.run(["xset", "+dpms"], check=True, capture_output=True)
                subprocess.run([
                    "xset", "dpms",
                    str(DEFAULT_DPMS_STANDBY),
                    str(DEFAULT_DPMS_SUSPEND),
                    str(DEFAULT_DPMS_OFF),
                ], check=True, capture_output=True)
                logger.info(
                    f"No saved DPMS state; DPMS was disabled, applied defaults "
                    f"({DEFAULT_DPMS_STANDBY}/{DEFAULT_DPMS_SUSPEND}/{DEFAULT_DPMS_OFF})"
                )
            except Exception as e:
                logger.warning(f"Could not apply default DPMS settings: {e}")
        else:
            logger.info("No saved DPMS state to restore")
        return

    try:
        if state.get("enabled", True):
            subprocess.run(["xset", "+dpms"], check=True, capture_output=True)
            subprocess.run([
                "xset", "dpms",
                str(state.get("standby", 0)),
                str(state.get("suspend", 0)),
                str(state.get("off", 0)),
            ], check=True, capture_output=True)
            logger.info("Restored DPMS enabled state and timeouts")
        else:
            subprocess.run(["xset", "-dpms"], check=True, capture_output=True)
            logger.info("Restored DPMS disabled state")
        _clear_dpms_state(logger)
    except Exception as e:
        logger.warning(f"Could not restore DPMS state: {e}")


def switch_to_eink(display_mgr, helper, logger, scale=1.75, autoswitch_theme=True, enable_frontlight=True, brightness_level=4):
    logger.info("Switching to E-Ink...")

    _disable_dpms_for_eink(logger)

    if autoswitch_theme:
        set_xfce_theme(logger, THEME_HIGH_CONTRAST)

    if not display_mgr.enable_display(DISPLAY_EINK, scale=scale):
        logger.error("Failed to enable E-Ink display output")
        return False

    time.sleep(1.0)

    if not helper_command(helper, logger, "enable-eink"):
        logger.error("Rolling back: enabling OLED display")
        display_mgr.enable_display(DISPLAY_OLED, scale=scale)
        return False

    if enable_frontlight:
        helper_command(helper, logger, "enable-frontlight", brightness_level=brightness_level)

    time.sleep(0.5)

    disable_ok = display_mgr.disable_display(DISPLAY_OLED)
    if not disable_ok:
        logger.warning("Failed to disable OLED output; continuing with final reconcile")

    if not display_mgr.finalize_single_display(DISPLAY_EINK, scale=scale):
        logger.error("Failed to finalize E-Ink output layout")
        return False

    if not disable_ok:
        logger.warning("E-Ink switch converged after OLED disable failure")

    if not _apply_input_mode(logger, "eink"):
        logger.warning("Failed to apply E-Ink input mode; continuing display switch")

    apply_stored_orientation(display_mgr, logger, target="eink")
    reconcile_touch(logger, display_mgr, target="eink", reason="switch_to_eink")
    _log_post_switch_display_snapshot(logger, "switch_to_eink")

    logger.info("Now using E-Ink")
    return True


def switch_to_oled(display_mgr, helper, logger, scale=1.75, autoswitch_theme=True, script_dir="."):
    logger.info("Switching to OLED...")

    image_process = None
    image_path = _resolve_privacy_image_path(script_dir)
    if image_path:
        logger.info("Displaying privacy image on E-Ink...")
        image_process = display_mgr.display_fullscreen_image(DISPLAY_EINK, image_path)
        if image_process:
            time.sleep(0.5)
        else:
            logger.warning("Could not display privacy image")
    else:
        logger.warning(f"Privacy image not found: {EINK_DISABLED_IMAGE}")

    if not helper_command(helper, logger, "disable-eink"):
        if image_process:
            try:
                image_process.terminate()
            except Exception:
                pass
        return False

    helper_command(helper, logger, "disable-frontlight")

    time.sleep(2.0)

    if image_process:
        try:
            image_process.terminate()
            image_process.wait(timeout=2)
        except Exception:
            try:
                image_process.kill()
            except Exception:
                pass

    if not display_mgr.enable_display(DISPLAY_OLED, scale=scale):
        logger.error("Failed to enable OLED output")
        return False

    time.sleep(1.0)

    if autoswitch_theme:
        set_xfce_theme(logger, THEME_ADWAITA_DARK)

    disable_ok = display_mgr.disable_display(DISPLAY_EINK)
    if not disable_ok:
        logger.warning("Failed to disable E-Ink output; continuing with final reconcile")

    if not display_mgr.finalize_single_display(DISPLAY_OLED, scale=scale):
        logger.error("Failed to finalize OLED output layout")
        return False

    if not disable_ok:
        logger.warning("OLED switch converged after E-Ink disable failure")

    _restore_dpms_after_eink(logger)

    if not _apply_input_mode(logger, "oled"):
        logger.warning("Failed to apply OLED input mode; continuing display switch")

    apply_stored_orientation(display_mgr, logger, target="oled")
    reconcile_touch(logger, display_mgr, target="oled", reason="switch_to_oled")
    _log_post_switch_display_snapshot(logger, "switch_to_oled")

    logger.info("Now using OLED")
    return True
