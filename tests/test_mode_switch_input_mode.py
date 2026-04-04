import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import mode_switch


class ApplyInputModeTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.devices = [
            {"id": 13, "name": "ITE Tech. Inc. ITE T-CON Pen stylus"},
            {"id": 14, "name": "ITE Tech. Inc. ITE T-CON Finger touch"},
            {"id": 21, "name": "Wacom HID 537D Pen stylus"},
            {"id": 22, "name": "Wacom HID 537D Finger touch"},
        ]

    def test_run_xinput_logs_command_and_success(self):
        completed = subprocess.CompletedProcess(
            ["xinput", "enable", "13"],
            0,
            stdout="done\n",
            stderr="",
        )

        with patch.object(mode_switch.subprocess, "run", return_value=completed):
            output = mode_switch._run_xinput(self.logger, ["enable", "13"])

        self.assertEqual(output, "done\n")
        self.logger.info.assert_has_calls([
            call("Running xinput enable 13"),
            call("xinput enable 13 succeeded: done"),
        ])

    def test_run_xinput_logs_detailed_failure(self):
        error = subprocess.CalledProcessError(
            1,
            ["xinput", "map-to-output", "13", "eDP-2"],
            output="partial stdout",
            stderr="bad things",
        )

        with patch.object(mode_switch.subprocess, "run", side_effect=error):
            output = mode_switch._run_xinput(self.logger, ["map-to-output", "13", "eDP-2"])

        self.assertIsNone(output)
        self.logger.info.assert_called_once_with("Running xinput map-to-output 13 eDP-2")
        self.logger.warning.assert_called_once_with(
            "xinput map-to-output 13 eDP-2 failed (rc=1): stderr=bad things; stdout=partial stdout"
        )

    def test_list_xinput_devices_normalizes_floating_prefixes(self):
        output = (
            "∼ ITE Tech. Inc. ITE T-CON                \tid=13\t[floating slave]\n"
            "⎜   ↳ Wacom HID 537D Finger touch          \tid=18\t[slave  pointer  (2)]\n"
        )

        with patch.object(mode_switch, "_run_xinput", return_value=output):
            devices = mode_switch._list_xinput_devices(self.logger)

        self.assertEqual(devices, [
            {"id": 13, "name": "ITE Tech. Inc. ITE T-CON"},
            {"id": 18, "name": "Wacom HID 537D Finger touch"},
        ])

    def test_expected_touch_ids_for_eink_target_uses_ite_devices(self):
        expected_ids = mode_switch._expected_touch_ids_for_target(self.devices, "eink")

        self.assertEqual(expected_ids, [13, 14])

    def test_expected_touch_ids_for_oled_target_uses_wacom_devices(self):
        expected_ids = mode_switch._expected_touch_ids_for_target(self.devices, "oled")

        self.assertEqual(expected_ids, [21, 22])

    def test_touch_health_is_healthy_when_any_expected_device_is_enabled(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices), \
             patch.object(mode_switch, "_get_device_enabled_state", side_effect=[0, 1]) as enabled_state:
            healthy = mode_switch._is_touch_healthy_for_target(self.logger, "eink")

        self.assertTrue(healthy)
        enabled_state.assert_has_calls([
            call(self.logger, 13),
            call(self.logger, 14),
        ])

    def test_touch_health_is_busted_when_all_expected_devices_are_disabled(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices), \
             patch.object(mode_switch, "_get_device_enabled_state", side_effect=[0, 0]) as enabled_state:
            healthy = mode_switch._is_touch_healthy_for_target(self.logger, "eink")

        self.assertFalse(healthy)
        enabled_state.assert_has_calls([
            call(self.logger, 13),
            call(self.logger, 14),
        ])

    def test_apply_input_mode_eink_enables_ite_disables_wacom_and_maps_to_eink_output(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices) as list_devices, \
             patch.object(mode_switch, "_set_input_enabled", return_value=True) as set_enabled, \
             patch.object(mode_switch, "_map_input_to_output", return_value=True, create=True) as map_output:
            result = mode_switch._apply_input_mode(self.logger, "eink")

        self.assertTrue(result)
        list_devices.assert_called_once_with(self.logger)
        set_enabled.assert_has_calls([
            call(self.logger, 13, True),
            call(self.logger, 14, True),
            call(self.logger, 21, False),
            call(self.logger, 22, False),
        ])
        map_output.assert_has_calls([
            call(self.logger, 13, mode_switch.DISPLAY_EINK),
            call(self.logger, 14, mode_switch.DISPLAY_EINK),
        ])

    def test_apply_input_mode_oled_maps_enabled_wacom_devices_to_oled_output(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices), \
             patch.object(mode_switch, "_set_input_enabled", return_value=True), \
             patch.object(mode_switch, "_map_input_to_output", return_value=True, create=True) as map_output:
            result = mode_switch._apply_input_mode(self.logger, "oled")

        self.assertTrue(result)
        map_output.assert_has_calls([
            call(self.logger, 21, mode_switch.DISPLAY_OLED),
            call(self.logger, 22, mode_switch.DISPLAY_OLED),
        ])

    def test_apply_input_mode_returns_false_when_mapping_fails(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices), \
             patch.object(mode_switch, "_set_input_enabled", return_value=True), \
             patch.object(mode_switch, "_map_input_to_output", side_effect=[False, True], create=True):
            result = mode_switch._apply_input_mode(self.logger, "eink")

        self.assertFalse(result)

    def test_apply_input_mode_logs_summary(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=self.devices), \
             patch.object(mode_switch, "_set_input_enabled", return_value=True), \
             patch.object(mode_switch, "_map_input_to_output", return_value=True, create=True):
            result = mode_switch._apply_input_mode(self.logger, "eink")

        self.assertTrue(result)
        self.logger.info.assert_any_call(
            "Input mode eink: matched E-Ink devices [13, 14], OLED devices [21, 22]"
        )
        self.logger.info.assert_any_call(
            "Input mode eink: target_output=eDP-2 enable_ids=[13, 14] disable_ids=[21, 22]"
        )
        self.logger.info.assert_any_call("Input mode eink applied successfully")

    def test_apply_input_mode_returns_false_when_no_devices_found(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=[]), \
             patch.object(mode_switch, "_set_input_enabled") as set_enabled, \
             patch.object(mode_switch, "_map_input_to_output", create=True) as map_output:
            result = mode_switch._apply_input_mode(self.logger, "eink")

        self.assertFalse(result)
        set_enabled.assert_not_called()
        map_output.assert_not_called()
        self.logger.warning.assert_called_once_with("No xinput devices found; skipping input mode update")

    def test_ensure_touch_available_does_nothing_when_touch_is_healthy(self):
        with patch.object(mode_switch, "_is_touch_healthy_for_target", return_value=True) as healthy, \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode:
            ok = mode_switch.ensure_touch_available(self.logger, "eink")

        self.assertTrue(ok)
        healthy.assert_called_once_with(self.logger, "eink")
        apply_input_mode.assert_not_called()

    def test_ensure_touch_available_reapplies_input_mode_when_touch_is_busted(self):
        with patch.object(mode_switch, "_is_touch_healthy_for_target", side_effect=[False, True]), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True) as apply_input_mode:
            ok = mode_switch.ensure_touch_available(self.logger, "eink")

        self.assertTrue(ok)
        apply_input_mode.assert_called_once_with(self.logger, "eink")

    def test_ensure_touch_available_verifies_again_after_reapply(self):
        with patch.object(mode_switch, "_is_touch_healthy_for_target", side_effect=[False, True]) as healthy, \
             patch.object(mode_switch, "_apply_input_mode", return_value=True):
            mode_switch.ensure_touch_available(self.logger, "oled")

        self.assertEqual(healthy.call_count, 2)
        healthy.assert_has_calls([
            call(self.logger, "oled"),
            call(self.logger, "oled"),
        ])

    def test_ensure_touch_available_logs_warning_when_touch_stays_busted(self):
        with patch.object(mode_switch, "_is_touch_healthy_for_target", side_effect=[False, False]), \
             patch.object(mode_switch, "_apply_input_mode", return_value=True):
            ok = mode_switch.ensure_touch_available(self.logger, "eink")

        self.assertFalse(ok)
        self.logger.warning.assert_any_call("Touch still unavailable for eink after input remap retry")


if __name__ == "__main__":
    unittest.main()
