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
DISPLAY_POWER_SAVED_STATE_KEY = "display_power_saved_state"
LEGACY_DPMS_SAVED_STATE_KEY = "dpms_saved_state"
XFCE_POWER_MANAGER_CHANNEL = "xfce4-power-manager"
XFCE_POWER_MANAGER_KEYS = {
    "/xfce4-power-manager/dpms-enabled": "bool",
    "/xfce4-power-manager/blank-on-ac": "int",
    "/xfce4-power-manager/blank-on-battery": "int",
    "/xfce4-power-manager/dpms-on-ac-sleep": "int",
    "/xfce4-power-manager/dpms-on-ac-off": "int",
    "/xfce4-power-manager/pre-blank-command": "string",
}
XFCE_EINK_POWER_POLICY = {
    "/xfce4-power-manager/dpms-enabled": "false",
    "/xfce4-power-manager/blank-on-ac": "0",
    "/xfce4-power-manager/blank-on-battery": "0",
    "/xfce4-power-manager/dpms-on-ac-sleep": "0",
    "/xfce4-power-manager/dpms-on-ac-off": "0",
}
EINK_INPUT_PATTERNS = ["ITE Tech. Inc. ITE T-CON*"]
OLED_INPUT_PATTERNS = ["Wacom HID 537D*"]
SUPPORTED_ORIENTATION_ROTATIONS = {"normal", "left"}
ORIENTATION_PREFERENCE_KEY = "orientation_preference"


def _build_switch_target(mode):
    if mode == "oled":
        return {
            "mode": "oled",
            "target_output": DISPLAY_OLED,
            "other_output": DISPLAY_EINK,
            "theme": THEME_ADWAITA_DARK,
            "input_target": "oled",
            "snapshot_reason": "switch_to_oled",
        }
    if mode == "eink":
        return {
            "mode": "eink",
            "target_output": DISPLAY_EINK,
            "other_output": DISPLAY_OLED,
            "theme": THEME_HIGH_CONTRAST,
            "input_target": "eink",
            "snapshot_reason": "switch_to_eink",
        }
    raise ValueError(f"Unsupported switch target mode: {mode}")


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


def _converge_single_display(display_mgr, logger, switch_target, scale):
    mode = switch_target["mode"]
    target_output = switch_target["target_output"]
    other_output = switch_target["other_output"]

    if not display_mgr.enable_display(target_output, scale=scale):
        logger.error(
            f"Display convergence failed for mode={mode} step=enable "
            f"target_output={target_output} other_output={other_output}"
        )
        return False

    if not display_mgr.disable_display(other_output):
        logger.error(
            f"Display convergence failed for mode={mode} step=disable "
            f"target_output={target_output} other_output={other_output}"
        )
        return False

    if not display_mgr.finalize_single_display(target_output, scale=scale):
        logger.error(
            f"Display convergence failed for mode={mode} step=finalize "
            f"target_output={target_output} other_output={other_output}"
        )
        return False

    return True


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


def _capture_xset_display_power_state(logger):
    try:
        result = subprocess.run(["xset", "q"], check=True, capture_output=True, text=True)
        output = result.stdout
    except Exception as e:
        logger.warning(f"Could not query display power state via xset: {e}")
        return None

    screensaver_timeout = screensaver_cycle = None
    dpms_enabled = None
    dpms_standby = dpms_suspend = dpms_off = None

    m_screensaver = re.search(r"timeout:\s*(\d+)\s+cycle:\s*(\d+)", output)
    if m_screensaver:
        screensaver_timeout = int(m_screensaver.group(1))
        screensaver_cycle = int(m_screensaver.group(2))

    m_enabled = re.search(r"DPMS is\s+(Enabled|Disabled)", output)
    if m_enabled:
        dpms_enabled = (m_enabled.group(1) == "Enabled")

    m_timeouts = re.search(r"Standby:\s*(\d+)\s+Suspend:\s*(\d+)\s+Off:\s*(\d+)", output)
    if m_timeouts:
        dpms_standby = int(m_timeouts.group(1))
        dpms_suspend = int(m_timeouts.group(2))
        dpms_off = int(m_timeouts.group(3))

    if (
        screensaver_timeout is None
        or screensaver_cycle is None
        or dpms_enabled is None
        or dpms_standby is None
        or dpms_suspend is None
        or dpms_off is None
    ):
        logger.warning("Could not parse full display power state from xset output")
        return None

    return {
        "screensaver_timeout": screensaver_timeout,
        "screensaver_cycle": screensaver_cycle,
        "dpms_enabled": dpms_enabled,
        "dpms_standby": dpms_standby,
        "dpms_suspend": dpms_suspend,
        "dpms_off": dpms_off,
    }


def _coerce_xfce_value(value_type, raw_value):
    value = raw_value.strip()
    if value_type == "bool":
        return value.lower() in ("1", "true", "yes")
    if value_type == "int":
        return int(value)
    return value


def _format_xfce_value(saved_value):
    value_type = saved_value.get("type")
    value = saved_value.get("value")
    if value_type == "bool":
        return "true" if value else "false"
    return str(value)


def _run_xfce_power_manager_query(logger, key):
    try:
        result = subprocess.run([
            "xfconf-query", "-c", XFCE_POWER_MANAGER_CHANNEL, "-p", key,
        ], check=True, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        logger.warning(f"Could not query XFCE power-manager key {key}: {e}")
        return None


def _run_xfce_power_manager_set(logger, key, value):
    try:
        subprocess.run([
            "xfconf-query", "-c", XFCE_POWER_MANAGER_CHANNEL, "-p", key, "-s", value,
        ], check=True, capture_output=True, text=True)
        return True
    except Exception as e:
        logger.warning(f"Could not set XFCE power-manager key {key}={value}: {e}")
        return False


def _capture_xfce_power_manager_state(logger):
    state = {}
    for key, value_type in XFCE_POWER_MANAGER_KEYS.items():
        raw_value = _run_xfce_power_manager_query(logger, key)
        if raw_value is None:
            continue
        try:
            state[key] = {
                "type": value_type,
                "value": _coerce_xfce_value(value_type, raw_value),
            }
        except Exception as e:
            logger.warning(f"Could not parse XFCE power-manager key {key}: {e}")
    return state


def _capture_display_power_state(logger):
    state = {}
    xset_state = _capture_xset_display_power_state(logger)
    if xset_state:
        state["xset"] = xset_state

    xfce_state = _capture_xfce_power_manager_state(logger)
    if xfce_state:
        state["xfce_power_manager"] = xfce_state

    return state if state else None


def _save_display_power_state(logger, display_power_state):
    settings = _load_settings(logger)
    settings[DISPLAY_POWER_SAVED_STATE_KEY] = display_power_state
    if LEGACY_DPMS_SAVED_STATE_KEY in settings:
        del settings[LEGACY_DPMS_SAVED_STATE_KEY]
    _save_settings(logger, settings)


def _load_display_power_state(logger):
    settings = _load_settings(logger)
    value = settings.get(DISPLAY_POWER_SAVED_STATE_KEY)
    if isinstance(value, dict):
        return value

    legacy = settings.get(LEGACY_DPMS_SAVED_STATE_KEY)
    if isinstance(legacy, dict):
        return {
            "legacy_dpms": legacy,
        }
    return None


def _has_saved_display_power_state(logger):
    settings = _load_settings(logger)
    return isinstance(settings.get(DISPLAY_POWER_SAVED_STATE_KEY), dict)


def _clear_display_power_state(logger):
    settings = _load_settings(logger)
    changed = False
    for key in (DISPLAY_POWER_SAVED_STATE_KEY, LEGACY_DPMS_SAVED_STATE_KEY):
        if key in settings:
            del settings[key]
            changed = True
    if changed:
        _save_settings(logger, settings)


def _apply_eink_display_power_policy(logger):
    try:
        subprocess.run(["xset", "s", "off"], check=True, capture_output=True)
        logger.info("Disabled X11 screensaver for E-Ink mode")
    except Exception as e:
        logger.warning(f"Could not disable X11 screensaver: {e}")

    try:
        subprocess.run(["xset", "-dpms"], check=True, capture_output=True)
        logger.info("Disabled DPMS for E-Ink mode")
    except Exception as e:
        logger.warning(f"Could not disable DPMS: {e}")

    for key, value in XFCE_EINK_POWER_POLICY.items():
        _run_xfce_power_manager_set(logger, key, value)


def _restore_xset_display_power_state(logger, state):
    subprocess.run([
        "xset", "s",
        str(state.get("screensaver_timeout", 0)),
        str(state.get("screensaver_cycle", 0)),
    ], check=True, capture_output=True)

    if state.get("dpms_enabled", True):
        subprocess.run(["xset", "+dpms"], check=True, capture_output=True)
        subprocess.run([
            "xset", "dpms",
            str(state.get("dpms_standby", 0)),
            str(state.get("dpms_suspend", 0)),
            str(state.get("dpms_off", 0)),
        ], check=True, capture_output=True)
    else:
        subprocess.run(["xset", "-dpms"], check=True, capture_output=True)


def _restore_legacy_dpms_state(logger, state):
    if state.get("enabled", True):
        subprocess.run(["xset", "+dpms"], check=True, capture_output=True)
        subprocess.run([
            "xset", "dpms",
            str(state.get("standby", 0)),
            str(state.get("suspend", 0)),
            str(state.get("off", 0)),
        ], check=True, capture_output=True)
    else:
        subprocess.run(["xset", "-dpms"], check=True, capture_output=True)


def _restore_xfce_power_manager_state(logger, state):
    for key, saved_value in state.items():
        _run_xfce_power_manager_set(logger, key, _format_xfce_value(saved_value))


def _disable_dpms_for_eink(logger):
    if not _has_saved_display_power_state(logger):
        state = _capture_display_power_state(logger)
        if state:
            _save_display_power_state(logger, state)
            logger.info("Saved display power policy for OLED mode")
    else:
        logger.info("Display power policy already saved; not overwriting OLED snapshot")

    _apply_eink_display_power_policy(logger)


def _restore_dpms_after_eink(logger):
    state = _load_display_power_state(logger)

    if not state:
        current = _capture_xset_display_power_state(logger)
        if current and not current.get("dpms_enabled", True):
            try:
                subprocess.run(["xset", "+dpms"], check=True, capture_output=True)
                subprocess.run([
                    "xset", "dpms",
                    str(DEFAULT_DPMS_STANDBY),
                    str(DEFAULT_DPMS_SUSPEND),
                    str(DEFAULT_DPMS_OFF),
                ], check=True, capture_output=True)
                logger.info(
                    f"No saved display power policy; DPMS was disabled, applied defaults "
                    f"({DEFAULT_DPMS_STANDBY}/{DEFAULT_DPMS_SUSPEND}/{DEFAULT_DPMS_OFF})"
                )
            except Exception as e:
                logger.warning(f"Could not apply default DPMS settings: {e}")
        else:
            logger.info("No saved display power policy to restore")
        return

    try:
        if "xset" in state:
            _restore_xset_display_power_state(logger, state["xset"])
            logger.info("Restored X11 screensaver and DPMS policy")
        if "legacy_dpms" in state:
            _restore_legacy_dpms_state(logger, state["legacy_dpms"])
            logger.info("Restored legacy DPMS policy")
        if "xfce_power_manager" in state:
            _restore_xfce_power_manager_state(logger, state["xfce_power_manager"])
            logger.info("Restored XFCE power-manager policy")
        _clear_display_power_state(logger)
    except Exception as e:
        logger.warning(f"Could not restore display power policy: {e}")


def switch_to_eink(display_mgr, helper, logger, scale=1.75, autoswitch_theme=True, enable_frontlight=True, brightness_level=4):
    logger.info("Switching to E-Ink...")
    switch_target = _build_switch_target("eink")
    converged = False

    try:
        if not helper_command(helper, logger, "enable-eink"):
            return False

        if enable_frontlight:
            helper_command(helper, logger, "enable-frontlight", brightness_level=brightness_level)

        time.sleep(0.5)
    except Exception as e:
        logger.error(f"E-Ink preparation failed: {e}")
        return False

    try:
        converged = _converge_single_display(display_mgr, logger, switch_target, scale)
        if not converged:
            return False
    except Exception as e:
        logger.error(f"E-Ink display convergence failed: {e}")
        return False

    try:
        _disable_dpms_for_eink(logger)

        if autoswitch_theme:
            set_xfce_theme(logger, switch_target["theme"])

        if not _apply_input_mode(logger, switch_target["input_target"]):
            logger.warning("Failed to apply E-Ink input mode; continuing display switch")

        apply_stored_orientation(display_mgr, logger, target=switch_target["input_target"])
        reconcile_touch(
            logger,
            display_mgr,
            target=switch_target["input_target"],
            reason=switch_target["snapshot_reason"],
        )
        _log_post_switch_display_snapshot(logger, switch_target["snapshot_reason"])
    except Exception as e:
        logger.warning(f"E-Ink post-convergence follow-up failed: {e}")

    if converged:
        logger.info("Now using E-Ink")
    return converged


def switch_to_oled(display_mgr, helper, logger, scale=1.75, autoswitch_theme=True, script_dir="."):
    logger.info("Switching to OLED...")
    switch_target = _build_switch_target("oled")
    image_process = None
    converged = False

    try:
        try:
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
                return False

            helper_command(helper, logger, "disable-frontlight")
            time.sleep(2.0)
        except Exception as e:
            logger.error(f"OLED preparation failed: {e}")
            return False

        try:
            converged = _converge_single_display(display_mgr, logger, switch_target, scale)
            if not converged:
                return False
        except Exception as e:
            logger.error(f"OLED display convergence failed: {e}")
            return False

        try:
            if autoswitch_theme:
                set_xfce_theme(logger, switch_target["theme"])

            _restore_dpms_after_eink(logger)

            if not _apply_input_mode(logger, switch_target["input_target"]):
                logger.warning("Failed to apply OLED input mode; continuing display switch")

            apply_stored_orientation(display_mgr, logger, target=switch_target["input_target"])
            reconcile_touch(
                logger,
                display_mgr,
                target=switch_target["input_target"],
                reason=switch_target["snapshot_reason"],
            )
            _log_post_switch_display_snapshot(logger, switch_target["snapshot_reason"])
        except Exception as e:
            logger.warning(f"OLED post-convergence follow-up failed: {e}")

        if converged:
            logger.info("Now using OLED")
        return converged
    finally:
        if image_process:
            try:
                image_process.terminate()
                image_process.wait(timeout=2)
            except Exception:
                try:
                    image_process.kill()
                except Exception:
                    pass
