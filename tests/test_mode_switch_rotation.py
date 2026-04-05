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


class SingleDisplayConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.display_mgr = MagicMock()
        self.display_mgr.enable_display.return_value = True
        self.display_mgr.disable_display.return_value = True
        self.display_mgr.finalize_single_display.return_value = True

    def test_converge_single_display_runs_critical_steps_in_order(self):
        target = mode_switch._build_switch_target("oled")

        ok = mode_switch._converge_single_display(self.display_mgr, self.logger, target, scale=1.75)

        self.assertTrue(ok)
        self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
        self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_EINK)
        self.display_mgr.finalize_single_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
        calls = self.display_mgr.mock_calls
        self.assertLess(
            calls.index(call.enable_display(mode_switch.DISPLAY_OLED, scale=1.75)),
            calls.index(call.disable_display(mode_switch.DISPLAY_EINK)),
        )
        self.assertLess(
            calls.index(call.disable_display(mode_switch.DISPLAY_EINK)),
            calls.index(call.finalize_single_display(mode_switch.DISPLAY_OLED, scale=1.75)),
        )

    def test_converge_single_display_fails_fast_when_critical_step_fails(self):
        target = mode_switch._build_switch_target("eink")
        self.display_mgr.disable_display.return_value = False

        ok = mode_switch._converge_single_display(self.display_mgr, self.logger, target, scale=1.75)

        self.assertFalse(ok)
        self.display_mgr.finalize_single_display.assert_not_called()

    def test_converge_single_display_logs_mode_outputs_and_failed_step(self):
        target = mode_switch._build_switch_target("oled")
        self.display_mgr.finalize_single_display.return_value = False

        ok = mode_switch._converge_single_display(self.display_mgr, self.logger, target, scale=1.75)

        self.assertFalse(ok)
        self.logger.error.assert_any_call(
            "Display convergence failed for mode=oled step=finalize target_output=eDP-1 other_output=eDP-2"
        )


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
        self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_EINK, scale=1.75)
        self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_OLED)
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
             patch.object(mode_switch, "reconcile_touch", return_value=True), \
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
        self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
        self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_EINK)
        self.display_mgr.set_display_rotation.assert_called_once_with(mode_switch.DISPLAY_OLED, "normal")
        apply_input_mode.assert_called_once_with(self.logger, "oled")

    def test_switch_to_eink_runs_touch_recovery_after_switch(self):
        with patch.object(mode_switch, "_disable_dpms_for_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "reconcile_touch", return_value=True) as reconcile_touch, \
             patch.object(mode_switch, "_log_post_switch_display_snapshot") as log_snapshot, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
                enable_frontlight=False,
            )

        self.assertTrue(ok)
        reconcile_touch.assert_called_once_with(
            self.logger,
            self.display_mgr,
            target="eink",
            reason="switch_to_eink",
        )
        log_snapshot.assert_called_once_with(self.logger, "switch_to_eink")

    def test_switch_to_eink_finalizes_single_output_after_disabling_oled(self):
        with patch.object(mode_switch, "_disable_dpms_for_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "reconcile_touch", return_value=True), \
             patch.object(mode_switch, "_log_post_switch_display_snapshot"), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
                enable_frontlight=False,
            )

        self.assertTrue(ok)
        self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_EINK, scale=1.75)
        self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_OLED)
        self.display_mgr.finalize_single_display.assert_called_once_with(mode_switch.DISPLAY_EINK, scale=1.75)

        calls = self.display_mgr.mock_calls
        disable_index = calls.index(call.disable_display(mode_switch.DISPLAY_OLED))
        finalize_index = calls.index(call.finalize_single_display(mode_switch.DISPLAY_EINK, scale=1.75))
        self.assertGreater(finalize_index, disable_index)

    def test_switch_to_oled_runs_touch_recovery_after_switch(self):
        with patch.object(mode_switch, "_restore_dpms_after_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "reconcile_touch", return_value=False) as reconcile_touch, \
             patch.object(mode_switch, "_log_post_switch_display_snapshot") as log_snapshot, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
            )

        self.assertTrue(ok)
        reconcile_touch.assert_called_once_with(
            self.logger,
            self.display_mgr,
            target="oled",
            reason="switch_to_oled",
        )
        log_snapshot.assert_called_once_with(self.logger, "switch_to_oled")

    def test_switch_to_oled_finalizes_single_output_after_disabling_eink(self):
        with patch.object(mode_switch, "_restore_dpms_after_eink"), \
             patch.object(mode_switch, "set_xfce_theme", return_value=True), \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True), \
             patch.object(mode_switch, "apply_stored_orientation", return_value=False), \
             patch.object(mode_switch, "reconcile_touch", return_value=False), \
             patch.object(mode_switch, "_log_post_switch_display_snapshot"), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=False,
            )

        self.assertTrue(ok)
        self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
        self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_EINK)
        self.display_mgr.finalize_single_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)

        calls = self.display_mgr.mock_calls
        disable_index = calls.index(call.disable_display(mode_switch.DISPLAY_EINK))
        finalize_index = calls.index(call.finalize_single_display(mode_switch.DISPLAY_OLED, scale=1.75))
        self.assertGreater(finalize_index, disable_index)

    def test_switch_to_oled_fails_fast_when_disabling_eink_fails(self):
        self.display_mgr.disable_display.return_value = False

        with patch.object(mode_switch, "_restore_dpms_after_eink") as restore_dpms, \
             patch.object(mode_switch, "set_xfce_theme", return_value=True) as set_theme, \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode, \
             patch.object(mode_switch, "apply_stored_orientation") as apply_orientation, \
             patch.object(mode_switch, "reconcile_touch") as reconcile_touch, \
             patch.object(mode_switch, "_log_post_switch_display_snapshot") as log_snapshot, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=True,
            )

        self.assertFalse(ok)
        self.display_mgr.finalize_single_display.assert_not_called()
        set_theme.assert_not_called()
        restore_dpms.assert_not_called()
        apply_input_mode.assert_not_called()
        apply_orientation.assert_not_called()
        reconcile_touch.assert_not_called()
        log_snapshot.assert_not_called()

    def test_switch_to_oled_cleans_up_privacy_image_when_convergence_fails(self):
        image_process = MagicMock()

        with patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_converge_single_display", return_value=False), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value="privacy.jpg"), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            self.display_mgr.display_fullscreen_image.return_value = image_process

            ok = mode_switch.switch_to_oled(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=True,
            )

        self.assertFalse(ok)
        image_process.terminate.assert_called_once()
        image_process.wait.assert_called_once_with(timeout=2)

    def test_switch_to_eink_fails_fast_when_disabling_oled_fails(self):
        self.display_mgr.disable_display.return_value = False

        with patch.object(mode_switch, "_disable_dpms_for_eink") as disable_dpms, \
             patch.object(mode_switch, "set_xfce_theme", return_value=True) as set_theme, \
             patch.object(mode_switch, "helper_command", return_value=True), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode, \
             patch.object(mode_switch, "apply_stored_orientation") as apply_orientation, \
             patch.object(mode_switch, "reconcile_touch") as reconcile_touch, \
             patch.object(mode_switch, "_log_post_switch_display_snapshot") as log_snapshot, \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                autoswitch_theme=True,
                enable_frontlight=False,
            )

        self.assertFalse(ok)
        self.display_mgr.finalize_single_display.assert_not_called()
        disable_dpms.assert_not_called()
        set_theme.assert_not_called()
        apply_input_mode.assert_not_called()
        apply_orientation.assert_not_called()
        reconcile_touch.assert_not_called()
        log_snapshot.assert_not_called()

    def test_switch_to_oled_defers_follow_up_work_until_after_display_convergence(self):
        events = []

        self.display_mgr.enable_display.side_effect = lambda *args, **kwargs: events.append("enable") or True
        self.display_mgr.disable_display.side_effect = lambda *args, **kwargs: events.append("disable") or True
        self.display_mgr.finalize_single_display.side_effect = lambda *args, **kwargs: events.append("finalize") or True

        with patch.object(mode_switch, "helper_command", side_effect=lambda *args, **kwargs: events.append(f"helper:{args[2]}") or True), \
             patch.object(mode_switch, "set_xfce_theme", side_effect=lambda *args, **kwargs: events.append("theme") or True), \
             patch.object(mode_switch, "_restore_dpms_after_eink", side_effect=lambda *args, **kwargs: events.append("restore-dpms")), \
             patch.object(mode_switch, "_apply_input_mode", side_effect=lambda *args, **kwargs: events.append("input") or True), \
             patch.object(mode_switch, "apply_stored_orientation", side_effect=lambda *args, **kwargs: events.append("orientation") or False), \
             patch.object(mode_switch, "reconcile_touch", side_effect=lambda *args, **kwargs: events.append("touch") or True), \
             patch.object(mode_switch, "_log_post_switch_display_snapshot", side_effect=lambda *args, **kwargs: events.append("snapshot")), \
             patch.object(mode_switch, "_resolve_privacy_image_path", return_value=None), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_oled(self.display_mgr, self.helper, self.logger)

        self.assertTrue(ok)
        self.assertLess(events.index("enable"), events.index("disable"))
        self.assertLess(events.index("disable"), events.index("finalize"))
        self.assertLess(events.index("finalize"), events.index("theme"))
        self.assertLess(events.index("finalize"), events.index("restore-dpms"))
        self.assertLess(events.index("finalize"), events.index("input"))
        self.assertLess(events.index("finalize"), events.index("orientation"))
        self.assertLess(events.index("finalize"), events.index("touch"))
        self.assertLess(events.index("finalize"), events.index("snapshot"))

    def test_switch_to_eink_defers_follow_up_work_until_after_display_convergence(self):
        events = []

        self.display_mgr.enable_display.side_effect = lambda *args, **kwargs: events.append("enable") or True
        self.display_mgr.disable_display.side_effect = lambda *args, **kwargs: events.append("disable") or True
        self.display_mgr.finalize_single_display.side_effect = lambda *args, **kwargs: events.append("finalize") or True

        def helper_side_effect(*args, **kwargs):
            events.append(f"helper:{args[2]}")
            return True

        with patch.object(mode_switch, "helper_command", side_effect=helper_side_effect), \
             patch.object(mode_switch, "_disable_dpms_for_eink", side_effect=lambda *args, **kwargs: events.append("disable-dpms")), \
             patch.object(mode_switch, "set_xfce_theme", side_effect=lambda *args, **kwargs: events.append("theme") or True), \
             patch.object(mode_switch, "_apply_input_mode", side_effect=lambda *args, **kwargs: events.append("input") or True), \
             patch.object(mode_switch, "apply_stored_orientation", side_effect=lambda *args, **kwargs: events.append("orientation") or False), \
             patch.object(mode_switch, "reconcile_touch", side_effect=lambda *args, **kwargs: events.append("touch") or True), \
             patch.object(mode_switch, "_log_post_switch_display_snapshot", side_effect=lambda *args, **kwargs: events.append("snapshot")), \
             patch.object(mode_switch.time, "sleep", return_value=None):
            ok = mode_switch.switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                enable_frontlight=False,
            )

        self.assertTrue(ok)
        self.assertLess(events.index("enable"), events.index("disable"))
        self.assertLess(events.index("disable"), events.index("finalize"))
        self.assertLess(events.index("finalize"), events.index("disable-dpms"))
        self.assertLess(events.index("finalize"), events.index("theme"))
        self.assertLess(events.index("finalize"), events.index("input"))
        self.assertLess(events.index("finalize"), events.index("orientation"))
        self.assertLess(events.index("finalize"), events.index("touch"))
        self.assertLess(events.index("finalize"), events.index("snapshot"))


if __name__ == "__main__":
    unittest.main()
