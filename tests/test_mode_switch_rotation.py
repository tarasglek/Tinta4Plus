import unittest
from unittest.mock import MagicMock, call, patch

import mode_switch


class OrientationPreferenceHelpersTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()

    def test_save_and_load_orientation_preference_round_trip(self):
        with patch.object(mode_switch, "_load_settings", return_value={}), \
             patch.object(mode_switch, "_save_settings", return_value=True) as save_settings:
            saved = mode_switch.save_orientation_preference(self.logger, "left")

        self.assertTrue(saved)
        save_settings.assert_called_once_with(self.logger, {"orientation_preference": "left"})

        with patch.object(mode_switch, "_load_settings", return_value={"orientation_preference": "normal"}):
            loaded = mode_switch.load_orientation_preference(self.logger)

        self.assertEqual(loaded, "normal")

    def test_load_orientation_preference_ignores_missing_or_unsupported_values(self):
        with patch.object(mode_switch, "_load_settings", return_value={}):
            self.assertIsNone(mode_switch.load_orientation_preference(self.logger))

        with patch.object(mode_switch, "_load_settings", return_value={"orientation_preference": "right"}):
            self.assertIsNone(mode_switch.load_orientation_preference(self.logger))


class ApplyStoredOrientationTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.display_mgr = MagicMock()

    def test_apply_stored_orientation_does_nothing_when_preference_missing(self):
        with patch.object(mode_switch, "load_orientation_preference", return_value=None):
            applied = mode_switch.apply_stored_orientation(self.display_mgr, self.logger, target="eink")

        self.assertFalse(applied)
        self.display_mgr.get_active_display.assert_not_called()
        self.display_mgr.set_display_rotation.assert_not_called()


class SwitchFlowOrientationTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.display_mgr = MagicMock()
        self.helper = MagicMock()

        self.display_mgr.enable_display.return_value = True
        self.display_mgr.disable_display.return_value = True

    def test_switch_to_eink_applies_stored_rotation_and_reapplies_input_mode(self):
        with patch.object(mode_switch, "_disable_dpms_for_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "load_orientation_preference", return_value="left"), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            self.display_mgr.get_active_display.return_value = mode_switch.DISPLAY_EINK
            self.display_mgr.set_display_rotation.return_value = True

            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
                enable_frontlight=False,
            )

        self.assertTrue(ok)
        self.display_mgr.set_display_rotation.assert_called_once_with(mode_switch.DISPLAY_EINK, "left")
        apply_input_mode.assert_has_calls([
            call(self.logger, "eink"),
            call(self.logger, "eink"),
        ])

    def test_switch_to_oled_stays_successful_when_orientation_apply_fails(self):
        with patch.object(mode_switch, "_restore_dpms_after_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch, "load_orientation_preference", return_value="normal"), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode, \
             patch.object(mode_switch, "ensure_touch_available", return_value=True), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            self.display_mgr.get_active_display.return_value = mode_switch.DISPLAY_OLED
            self.display_mgr.set_display_rotation.return_value = False

            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
            )

        self.assertTrue(ok)
        self.display_mgr.set_display_rotation.assert_called_once_with(mode_switch.DISPLAY_OLED, "normal")
        apply_input_mode.assert_called_once_with(self.logger, "oled")

    def test_switch_to_eink_runs_touch_recovery_after_switch(self):
        with patch.object(mode_switch, "_disable_dpms_for_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "ensure_touch_available", return_value=True) as ensure_touch, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
                enable_frontlight=False,
            )

        self.assertTrue(ok)
        ensure_touch.assert_called_once_with(self.logger, "eink")

    def test_switch_to_oled_runs_touch_recovery_after_switch(self):
        with patch.object(mode_switch, "_restore_dpms_after_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "ensure_touch_available", return_value=False) as ensure_touch, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
            )

        self.assertTrue(ok)
        ensure_touch.assert_called_once_with(self.logger, "oled")


if __name__ == "__main__":
    unittest.main()
