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


class DisplayManagerTargetStateTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.manager = DisplayManager(self.logger)

    def test_build_target_state_native_oled(self):
        target = self.manager._build_display_target_state("eDP-1", 1.0)

        self.assertEqual(target["display_name"], "eDP-1")
        self.assertEqual(target["native_width"], 2880)
        self.assertEqual(target["native_height"], 1800)
        self.assertEqual(target["xrandr_scale_x"], 1.0)
        self.assertEqual(target["xrandr_scale_y"], 1.0)
        self.assertEqual(target["logical_width"], 2880)
        self.assertEqual(target["logical_height"], 1800)
        self.assertEqual(target["panning_width"], 2880)
        self.assertEqual(target["panning_height"], 1800)
        self.assertEqual(target["framebuffer_width"], 2880)
        self.assertEqual(target["framebuffer_height"], 1800)

    def test_build_target_state_scaled_oled(self):
        target = self.manager._build_display_target_state("eDP-1", 1.5)

        self.assertAlmostEqual(target["xrandr_scale_x"], 1 / 1.5)
        self.assertAlmostEqual(target["xrandr_scale_y"], 1 / 1.5)
        self.assertEqual(target["logical_width"], 1920)
        self.assertEqual(target["logical_height"], 1200)
        self.assertEqual(target["panning_width"], 1920)
        self.assertEqual(target["panning_height"], 1200)
        self.assertEqual(target["framebuffer_width"], 1920)
        self.assertEqual(target["framebuffer_height"], 1200)

    def test_build_target_state_scaled_eink(self):
        target = self.manager._build_display_target_state("eDP-2", 1.75)

        self.assertAlmostEqual(target["xrandr_scale_x"], 1 / 1.75)
        self.assertAlmostEqual(target["xrandr_scale_y"], 1 / 1.75)
        self.assertEqual(target["logical_width"], 1463)
        self.assertEqual(target["logical_height"], 915)
        self.assertEqual(target["panning_width"], 1463)
        self.assertEqual(target["panning_height"], 915)
        self.assertEqual(target["framebuffer_width"], 1463)
        self.assertEqual(target["framebuffer_height"], 915)

    def test_apply_display_scale_builds_full_state_xrandr_command(self):
        with patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            ok = self.manager._apply_display_scale("eDP-1", scale=1.5)

        self.assertTrue(ok)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0:3], ["xrandr", "--output", "eDP-1"])
        self.assertIn("--mode", command)
        self.assertIn("2880x1800", command)
        self.assertIn("--scale", command)
        self.assertIn("0.6666666666666666x0.6666666666666666", command)
        self.assertIn("--panning", command)
        self.assertIn("1920x1200", command)
        self.assertIn("--fb", command)
        self.assertIn("1920x1200", command)

    def test_apply_display_scale_unknown_display_uses_auto(self):
        with patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            ok = self.manager._apply_display_scale("HDMI-9", scale=1.5)

        self.assertTrue(ok)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0:3], ["xrandr", "--output", "HDMI-9"])
        self.assertIn("--auto", command)

    def test_finalize_single_display_builds_compact_scaled_command(self):
        with patch("DisplayManager.subprocess.run") as run_mock, \
             patch.object(self.manager, "_verify_display_target_state", return_value=True), \
             patch("DisplayManager.time.sleep"):
            run_mock.return_value.returncode = 0
            ok = self.manager.finalize_single_display("eDP-2", scale=1.75)

        self.assertTrue(ok)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0:3], ["xrandr", "--output", "eDP-2"])
        self.assertIn("--mode", command)
        self.assertIn("2560x1600", command)
        self.assertIn("--scale", command)
        self.assertIn("0.5714285714285714x0.5714285714285714", command)
        self.assertIn("--panning", command)
        self.assertIn("1463x915", command)
        self.assertIn("--fb", command)
        self.assertIn("1463x915", command)


class DisplayManagerVerificationTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.manager = DisplayManager(self.logger)

    def _target_state(self):
        return {
            "display_name": "eDP-2",
            "logical_width": 1600,
            "logical_height": 1000,
            "framebuffer_width": 1600,
            "framebuffer_height": 1000,
        }

    def test_verify_display_target_state_success(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1600 x 1000, maximum 32767 x 32767
eDP-2 connected primary 1600x1000+0+0 normal (normal left inverted right x axis y axis)
""".strip()

        ok = self.manager._verify_display_target_state(
            "eDP-2", self._target_state(), xrandr_output=xrandr_output
        )

        self.assertTrue(ok)

    def test_verify_display_target_state_fails_when_framebuffer_too_small(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1500 x 900, maximum 32767 x 32767
eDP-2 connected primary 1600x1000+0+0 normal (normal left inverted right x axis y axis)
""".strip()

        ok = self.manager._verify_display_target_state(
            "eDP-2", self._target_state(), xrandr_output=xrandr_output
        )

        self.assertFalse(ok)

    def test_verify_display_target_state_fails_when_output_geometry_wrong(self):
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1600 x 1000, maximum 32767 x 32767
eDP-2 connected primary 1400x900+0+0 normal (normal left inverted right x axis y axis)
""".strip()

        ok = self.manager._verify_display_target_state(
            "eDP-2", self._target_state(), xrandr_output=xrandr_output
        )

        self.assertFalse(ok)

    def test_verify_display_target_state_succeeds_for_ceil_scaled_eink_layout(self):
        target_state = {
            "display_name": "eDP-2",
            "logical_width": 1463,
            "logical_height": 915,
            "framebuffer_width": 1463,
            "framebuffer_height": 915,
        }
        xrandr_output = """
Screen 0: minimum 8 x 8, current 1463 x 915, maximum 32767 x 32767
eDP-2 connected primary 1463x915+0+0 normal (normal left inverted right x axis y axis)
""".strip()

        ok = self.manager._verify_display_target_state(
            "eDP-2", target_state, xrandr_output=xrandr_output
        )

        self.assertTrue(ok)


class DisplayManagerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.manager = DisplayManager(self.logger)

    def test_enable_display_uses_transition_safe_activation_without_fb_resize(self):
        with patch.object(self.manager, "is_display_active", return_value=True), \
             patch.object(self.manager, "_get_xrandr_output", return_value=None), \
             patch("DisplayManager.time.sleep"), \
             patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            ok = self.manager.enable_display("eDP-1", scale=1.5)

        self.assertTrue(ok)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0:3], ["xrandr", "--output", "eDP-1"])
        self.assertIn("--mode", command)
        self.assertIn("2880x1800", command)
        self.assertIn("--scale", command)
        self.assertNotIn("--panning", command)
        self.assertNotIn("--fb", command)

    def test_enable_display_returns_false_when_output_not_active_after_apply(self):
        with patch.object(self.manager, "is_display_active", return_value=False), \
             patch.object(self.manager, "_get_xrandr_output", return_value=None), \
             patch("DisplayManager.time.sleep"), \
             patch("DisplayManager.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            ok = self.manager.enable_display("eDP-1", scale=1.5)

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
