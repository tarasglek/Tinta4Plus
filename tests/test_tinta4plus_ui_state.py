import unittest
from unittest.mock import MagicMock, patch

import Tinta4Plus


class FakeVar:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class FakeWidget:
    def __init__(self):
        self.props = {}

    def config(self, **kwargs):
        self.props.update(kwargs)

    def cget(self, key):
        return self.props.get(key)


class UiStateSyncTests(unittest.TestCase):
    def make_gui(self):
        gui = type("GuiStub", (), {})()
        gui.display_mgr = object()
        gui.eink_enabled_var = FakeVar(False)
        gui.eink_toggle_btn = FakeWidget()
        gui.btn_refresh = FakeWidget()
        gui.btn_set_dynamic = FakeWidget()
        gui.btn_set_reading = FakeWidget()
        gui._start_refresh_timer = MagicMock()
        gui._stop_refresh_timer = MagicMock()
        gui._ensure_floating_refresh_button = MagicMock()
        gui._destroy_floating_refresh_button = MagicMock()
        gui.log_message = MagicMock()
        gui.update_status = MagicMock()
        return gui

    def test_eink_state_enables_controls_and_refresh_lifecycle(self):
        gui = self.make_gui()

        with patch.object(Tinta4Plus, "get_display_state", return_value={"oled_active": False, "eink_active": True, "mode": "eink"}):
            Tinta4Plus.EInkControlGUI.sync_ui_from_display_state(gui)

        self.assertTrue(gui.eink_enabled_var.get())
        self.assertEqual(gui.eink_toggle_btn.cget("text"), "eInk Enabled")
        self.assertEqual(gui.btn_refresh.cget("state"), "normal")
        self.assertEqual(gui.btn_set_dynamic.cget("state"), "normal")
        self.assertEqual(gui.btn_set_reading.cget("state"), "normal")
        gui._start_refresh_timer.assert_called_once()
        gui._ensure_floating_refresh_button.assert_called_once()
        gui._stop_refresh_timer.assert_not_called()
        gui._destroy_floating_refresh_button.assert_not_called()

    def test_oled_state_disables_controls_and_refresh_lifecycle(self):
        gui = self.make_gui()

        with patch.object(Tinta4Plus, "get_display_state", return_value={"oled_active": True, "eink_active": False, "mode": "oled"}):
            Tinta4Plus.EInkControlGUI.sync_ui_from_display_state(gui)

        self.assertFalse(gui.eink_enabled_var.get())
        self.assertEqual(gui.eink_toggle_btn.cget("text"), "eInk Disabled")
        self.assertEqual(gui.btn_refresh.cget("state"), "disabled")
        self.assertEqual(gui.btn_set_dynamic.cget("state"), "disabled")
        self.assertEqual(gui.btn_set_reading.cget("state"), "disabled")
        gui._stop_refresh_timer.assert_called_once()
        gui._destroy_floating_refresh_button.assert_called_once()
        gui._start_refresh_timer.assert_not_called()
        gui._ensure_floating_refresh_button.assert_not_called()

    def test_unknown_or_mixed_state_stays_conservatively_disabled(self):
        gui = self.make_gui()

        with patch.object(Tinta4Plus, "get_display_state", return_value={"oled_active": True, "eink_active": True, "mode": "mixed"}):
            Tinta4Plus.EInkControlGUI.sync_ui_from_display_state(gui)

        self.assertFalse(gui.eink_enabled_var.get())
        self.assertEqual(gui.eink_toggle_btn.cget("text"), "eInk Disabled")
        self.assertEqual(gui.btn_refresh.cget("state"), "disabled")
        self.assertEqual(gui.btn_set_dynamic.cget("state"), "disabled")
        self.assertEqual(gui.btn_set_reading.cget("state"), "disabled")
        gui._stop_refresh_timer.assert_called_once()
        gui._destroy_floating_refresh_button.assert_called_once()
        gui.log_message.assert_called()


if __name__ == "__main__":
    unittest.main()
