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

    def test_apply_input_mode_returns_false_when_no_devices_found(self):
        with patch.object(mode_switch, "_list_xinput_devices", return_value=[]), \
             patch.object(mode_switch, "_set_input_enabled") as set_enabled, \
             patch.object(mode_switch, "_map_input_to_output", create=True) as map_output:
            result = mode_switch._apply_input_mode(self.logger, "eink")

        self.assertFalse(result)
        set_enabled.assert_not_called()
        map_output.assert_not_called()
        self.logger.warning.assert_called_once_with("No xinput devices found; skipping input mode update")


if __name__ == "__main__":
    unittest.main()
