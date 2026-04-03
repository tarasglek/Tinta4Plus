import unittest

import mode_switch


class FakeDisplayManager:
    def __init__(self, active_map):
        self.active_map = active_map

    def is_display_active(self, display_name):
        return self.active_map.get(display_name, False)


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


if __name__ == "__main__":
    unittest.main()
