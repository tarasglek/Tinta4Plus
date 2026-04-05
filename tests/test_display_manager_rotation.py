import unittest
from unittest.mock import MagicMock, patch

from DisplayManager import DisplayManager


class DisplayManagerRotationTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.manager = DisplayManager(self.logger)

    def test_get_active_display_detects_connected_output_with_geometry(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 2880 x 1800, maximum 32767 x 32767
eDP-1 connected primary 2880x1800+0+0 normal (normal left inverted right x axis y axis) 302mm x 189mm
eDP-2 connected (normal left inverted right x axis y axis)
""".strip()

        with patch.object(self.manager, "_get_xrandr_output", return_value=xrandr_output):
            active = self.manager.get_active_display()

        self.assertEqual(active, "eDP-1")

    def test_get_display_rotation_parses_normal_and_left(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1600 x 2560, maximum 32767 x 32767
eDP-1 connected (normal left inverted right x axis y axis)
eDP-2 connected primary 1600x2560+0+0 left (normal left inverted right x axis y axis)
""".strip()

        with patch.object(self.manager, "_get_xrandr_output", return_value=xrandr_output):
            oled_rotation = self.manager.get_display_rotation("eDP-1")
            eink_rotation = self.manager.get_display_rotation("eDP-2")

        self.assertEqual(oled_rotation, "normal")
        self.assertEqual(eink_rotation, "left")

    def test_get_display_rotation_returns_none_for_unsupported_rotation(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1800 x 2880, maximum 32767 x 32767
eDP-1 connected primary 1800x2880+0+0 right (normal left inverted right x axis y axis)
""".strip()

        with patch.object(self.manager, "_get_xrandr_output", return_value=xrandr_output):
            rotation = self.manager.get_display_rotation("eDP-1")

        self.assertIsNone(rotation)
        self.logger.warning.assert_called_once()

    def test_set_display_rotation_runs_xrandr_command_and_invalidates_cache(self):
        self.manager._xrandr_cache = "cached"
        self.manager._xrandr_cache_time = 123.0

        with patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            ok = self.manager.set_display_rotation("eDP-2", "left")

        self.assertTrue(ok)
        run_mock.assert_called_once_with(
            ["xrandr", "--output", "eDP-2", "--rotate", "left"],
            capture_output=True,
            timeout=self.manager.XRANDR_TIMEOUT,
        )
        self.assertIsNone(self.manager._xrandr_cache)

    def test_enable_display_lower_scale_resets_to_one_then_applies_target_scale(self):
        with patch.object(self.manager, "get_effective_display_scale", return_value=1.9, create=True), \
             patch.object(self.manager, "is_display_active", return_value=True), \
             patch("DisplayManager.time.sleep"), \
             patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            ok = self.manager.enable_display("eDP-1", scale=1.5)

        self.assertTrue(ok)
        self.assertEqual(run_mock.call_count, 2)

        first_cmd = run_mock.call_args_list[0].args[0]
        second_cmd = run_mock.call_args_list[1].args[0]

        self.assertEqual(first_cmd[0:3], ["xrandr", "--output", "eDP-1"])
        self.assertIn("--scale", first_cmd)
        self.assertIn("1x1", first_cmd)

        self.assertEqual(second_cmd[0:3], ["xrandr", "--output", "eDP-1"])
        self.assertIn("--scale", second_cmd)
        self.assertNotIn("1x1", second_cmd)

    def test_enable_display_higher_scale_applies_once(self):
        with patch.object(self.manager, "get_effective_display_scale", return_value=1.5, create=True), \
             patch.object(self.manager, "is_display_active", return_value=True), \
             patch("DisplayManager.time.sleep"), \
             patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            ok = self.manager.enable_display("eDP-1", scale=1.9)

        self.assertTrue(ok)
        self.assertEqual(run_mock.call_count, 1)

    def test_enable_display_unknown_current_scale_applies_once(self):
        with patch.object(self.manager, "get_effective_display_scale", return_value=None, create=True), \
             patch.object(self.manager, "is_display_active", return_value=True), \
             patch("DisplayManager.time.sleep"), \
             patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            ok = self.manager.enable_display("eDP-1", scale=1.5)

        self.assertTrue(ok)
        self.assertEqual(run_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
