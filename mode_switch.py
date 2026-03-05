#!/usr/bin/env python3
"""Shared OLED <-> E-Ink mode switching logic for GUI and CLI."""

import os
import subprocess
import time

DISPLAY_OLED = "eDP-1"
DISPLAY_EINK = "eDP-2"
THEME_HIGH_CONTRAST = "HighContrast"
THEME_ADWAITA_DARK = "Adwaita-dark"
EINK_DISABLED_IMAGE = "eink-disable.jpg"


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


def _resolve_privacy_image_path(script_dir):
    image_path = EINK_DISABLED_IMAGE
    if os.path.exists(image_path):
        return image_path

    image_path = os.path.join(script_dir, EINK_DISABLED_IMAGE)
    if os.path.exists(image_path):
        return image_path

    return None


def switch_to_eink(display_mgr, helper, logger, scale=1.75, autoswitch_theme=True, enable_frontlight=True, brightness_level=4):
    logger.info("Switching to E-Ink...")

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

    if not display_mgr.disable_display(DISPLAY_OLED):
        logger.error("Failed to disable OLED output")
        return False

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

    if not display_mgr.disable_display(DISPLAY_EINK):
        logger.error("Failed to disable E-Ink output")
        return False

    if autoswitch_theme:
        set_xfce_theme(logger, THEME_ADWAITA_DARK)

    logger.info("Now using OLED")
    return True
