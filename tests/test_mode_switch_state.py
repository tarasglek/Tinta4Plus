import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mode_switch


class FakeDisplayManager:
    def __init__(self, active_map):
        self.active_map = active_map

    def is_display_active(self, display_name):
        return self.active_map.get(display_name, False)


TOGGLE_EINK_PATH = Path(__file__).resolve().parent.parent / "toggle-eink.py"


def load_toggle_eink_module():
    module_name = "toggle_eink_cli"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, TOGGLE_EINK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class GetDisplayStateTests(unittest.TestCase):
    def test_only_edp2_active_reports_eink_mode(self):
        display_mgr = FakeDisplayManager({"eDP-1": False, "eDP-2": True})

        state = mode_switch.get_display_state(display_mgr)

        self.assertEqual(
            state,
            {
                "oled_active": False,
                "eink_active": True,
                "mode": "eink",
            },
        )

    def test_only_edp1_active_reports_oled_mode(self):
        display_mgr = FakeDisplayManager({"eDP-1": True, "eDP-2": False})

        state = mode_switch.get_display_state(display_mgr)

        self.assertEqual(
            state,
            {
                "oled_active": True,
                "eink_active": False,
                "mode": "oled",
            },
        )

    def test_both_displays_active_reports_mixed_mode(self):
        display_mgr = FakeDisplayManager({"eDP-1": True, "eDP-2": True})

        state = mode_switch.get_display_state(display_mgr)

        self.assertEqual(
            state,
            {
                "oled_active": True,
                "eink_active": True,
                "mode": "mixed",
            },
        )

    def test_neither_display_active_reports_unknown_mode(self):
        display_mgr = FakeDisplayManager({"eDP-1": False, "eDP-2": False})

        state = mode_switch.get_display_state(display_mgr)

        self.assertEqual(
            state,
            {
                "oled_active": False,
                "eink_active": False,
                "mode": "unknown",
            },
        )


class ToggleEinkCliStateTests(unittest.TestCase):
    def test_cli_uses_shared_state_mode_for_toggle_direction(self):
        toggle_eink = load_toggle_eink_module()

        logger = MagicMock()

        class FakeDisplayManager:
            def __init__(self, _logger):
                pass

            def is_display_active(self, _display_name):
                raise AssertionError("CLI must not read raw display activity directly")

        class FakeHelperClient:
            def __init__(self, _logger):
                self.connected = True

            def connect(self, _socket_path, timeout=10.0):
                return True

            def is_connected(self):
                return self.connected

            def disconnect(self):
                self.connected = False

        with patch.object(toggle_eink, "setup_logger", return_value=logger), \
             patch.object(toggle_eink, "DisplayManager", FakeDisplayManager), \
             patch.object(toggle_eink, "HelperClient", FakeHelperClient), \
             patch.object(toggle_eink, "load_settings", return_value={"display_scale": 1.75, "autoswitch_theme": True}), \
             patch.object(toggle_eink, "get_display_state", return_value={"oled_active": True, "eink_active": True, "mode": "mixed"}), \
             patch.object(toggle_eink, "switch_to_oled", return_value=True) as switch_to_oled, \
             patch.object(toggle_eink, "switch_to_eink", return_value=True) as switch_to_eink:
            exit_code = toggle_eink.main()

        self.assertEqual(exit_code, 0)
        switch_to_oled.assert_not_called()
        switch_to_eink.assert_called_once()


if __name__ == "__main__":
    unittest.main()
