#!/usr/bin/env python3
"""Minimal CLI toggle for ThinkBook Plus Gen4 OLED <-> E-Ink."""

import json
import logging
import os
import sys

from DisplayManager import DisplayManager
from HelperClient import HelperClient
from mode_switch import DISPLAY_EINK, switch_to_eink, switch_to_oled

SOCKET_PATH = "/run/tinta4plus.sock"
DEFAULT_SCALE = 1.75
CONFIG_DIR = os.path.expanduser("~/.config/Tinta4Plus")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings")


def setup_logger():
    logger = logging.getLogger("toggle-eink")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    return logger


def load_settings(logger):
    defaults = {
        "display_scale": DEFAULT_SCALE,
        "autoswitch_theme": True,
    }

    if not os.path.exists(SETTINGS_FILE):
        return defaults

    try:
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load settings, using defaults: {e}")
        return defaults

    return {
        "display_scale": settings.get("display_scale", defaults["display_scale"]),
        "autoswitch_theme": settings.get("autoswitch_theme", defaults["autoswitch_theme"]),
    }


def main():
    logger = setup_logger()
    display_mgr = DisplayManager(logger)
    helper = HelperClient(logger)

    try:
        if not helper.connect(SOCKET_PATH, timeout=10.0):
            logger.error("Could not connect to helper at /run/tinta4plus.sock")
            logger.error("Try: systemctl status tinta4plus-helper.socket")
            return 1

        settings = load_settings(logger)
        scale = settings["display_scale"]
        autoswitch_theme = settings["autoswitch_theme"]

        eink_active = display_mgr.is_display_active(DISPLAY_EINK)

        if eink_active:
            ok = switch_to_oled(
                display_mgr,
                helper,
                logger,
                scale=scale,
                autoswitch_theme=autoswitch_theme,
                script_dir=os.path.dirname(os.path.abspath(__file__)),
            )
        else:
            ok = switch_to_eink(
                display_mgr,
                helper,
                logger,
                scale=scale,
                autoswitch_theme=autoswitch_theme,
                enable_frontlight=True,
                brightness_level=4,
            )

        return 0 if ok else 1

    except Exception as e:
        logger.error(f"Toggle failed: {e}")
        return 1
    finally:
        try:
            if helper.is_connected():
                helper.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
