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


class FakeWarningWidget(FakeWidget):
    def __init__(self):
        super().__init__()
        self.grid_called = False
        self.grid_remove_called = False

    def grid(self, **_kwargs):
        self.grid_called = True

    def grid_remove(self):
        self.grid_remove_called = True


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


class GuiLifecycleSyncTests(unittest.TestCase):
    def test_initialize_helper_syncs_ui_after_successful_connect(self):
        gui = type("GuiStub", (), {})()
        gui._prompt_install_or_upgrade = MagicMock(return_value=True)
        gui.helper = MagicMock()
        gui.helper.connect.return_value = True
        gui.SOCKET_PATH = "/run/tinta4plus.sock"
        gui.SOCKET_TIMEOUT = 10.0
        gui.update_status = MagicMock()
        gui.log_message = MagicMock()
        gui.root = type("Root", (), {"after": MagicMock()})()
        gui.check_ec_status = MagicMock()
        gui.sync_ui_from_display_state = MagicMock()

        Tinta4Plus.EInkControlGUI.initialize_helper(gui)

        gui.sync_ui_from_display_state.assert_called_once()

    def test_attempt_helper_restart_syncs_ui_after_successful_reconnect(self):
        gui = type("GuiStub", (), {})()
        gui.log_message = MagicMock()
        gui.helper = MagicMock()
        gui.helper.is_connected.return_value = True
        gui.helper.connect.return_value = True
        gui.logger = MagicMock()
        gui.SOCKET_PATH = "/run/tinta4plus.sock"
        gui.SOCKET_TIMEOUT = 10.0
        gui.update_status = MagicMock()
        gui.root = type("Root", (), {"after": MagicMock()})()
        gui.check_ec_status = MagicMock()
        gui.sync_ui_from_display_state = MagicMock()

        with patch.object(Tinta4Plus.time, "sleep", return_value=None):
            Tinta4Plus.EInkControlGUI.attempt_helper_restart(gui)

        gui.sync_ui_from_display_state.assert_called_once()

    def test_toggle_to_eink_uses_sync_ui_on_success(self):
        gui = type("GuiStub", (), {})()
        gui.eink_enabled_var = FakeVar(False)
        gui.display_mgr = object()
        gui.helper = object()
        gui.logger = MagicMock()
        gui.display_scale = 1.75
        gui.autoswitch_theme_var = FakeVar(True)
        gui.brightness_var = FakeVar(4)
        gui.sync_ui_from_display_state = MagicMock()
        gui.log_message = MagicMock()
        gui.root = object()
        gui.on_refresh_full = MagicMock()
        gui.btn_refresh = FakeWidget()
        gui.btn_set_dynamic = FakeWidget()
        gui.btn_set_reading = FakeWidget()
        gui.eink_toggle_btn = FakeWidget()
        gui._start_refresh_timer = MagicMock()
        gui.floating_refresh_button = None
        gui.update_status = MagicMock()

        with patch.object(Tinta4Plus, "switch_to_eink", return_value=True), \
             patch.object(Tinta4Plus, "FloatingRefreshButton", MagicMock()):
            Tinta4Plus.EInkControlGUI.on_eink_toggled(gui)

        gui.sync_ui_from_display_state.assert_called_once()

    def test_toggle_to_oled_uses_sync_ui_on_success(self):
        gui = type("GuiStub", (), {})()
        gui.eink_enabled_var = FakeVar(True)
        gui.display_mgr = object()
        gui.helper = object()
        gui.logger = MagicMock()
        gui.display_scale = 1.75
        gui.autoswitch_theme_var = FakeVar(True)
        gui.sync_ui_from_display_state = MagicMock()
        gui.log_message = MagicMock()
        gui._stop_refresh_timer = MagicMock()
        gui.floating_refresh_button = None
        gui.btn_refresh = FakeWidget()
        gui.btn_set_dynamic = FakeWidget()
        gui.btn_set_reading = FakeWidget()
        gui.eink_toggle_btn = FakeWidget()
        gui.update_status = MagicMock()

        with patch.object(Tinta4Plus, "switch_to_oled", return_value=True):
            Tinta4Plus.EInkControlGUI.on_eink_toggled(gui)

        gui.sync_ui_from_display_state.assert_called_once()

    def test_on_closing_does_not_toggle_display_mode(self):
        gui = type("GuiStub", (), {})()
        gui.logger = MagicMock()
        gui.eink_enabled_var = FakeVar(True)
        gui.log_message = MagicMock()
        gui.on_eink_toggled = MagicMock()
        gui._stop_refresh_timer = MagicMock()
        gui.helper = MagicMock()
        gui.helper.is_connected.return_value = True
        gui.root = MagicMock()

        Tinta4Plus.EInkControlGUI.on_closing(gui)

        gui.on_eink_toggled.assert_not_called()
        gui._stop_refresh_timer.assert_called_once()
        gui.helper.disconnect.assert_called_once()
        gui.root.destroy.assert_called_once()


class OrientationUiTests(unittest.TestCase):
    def make_gui(self):
        gui = type("GuiStub", (), {})()
        gui.display_mgr = MagicMock()
        gui.orientation_toggle_btn = FakeWidget()
        gui.orientation_rotation = None
        gui.log_message = MagicMock()
        gui.update_status = MagicMock()
        gui.logger = MagicMock()
        return gui

    def test_sync_orientation_on_startup_updates_button_from_live_display_state(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = "eDP-1"
        gui.display_mgr.get_display_rotation.return_value = "left"

        Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)

        self.assertEqual(gui.orientation_rotation, "left")
        self.assertEqual(gui.orientation_toggle_btn.cget("text"), "Orientation: Portrait")
        self.assertEqual(gui.orientation_toggle_btn.cget("state"), "normal")

    def test_sync_orientation_disables_button_when_no_active_display(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = None

        Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)

        self.assertEqual(gui.orientation_toggle_btn.cget("state"), "disabled")

    def test_toggle_orientation_switches_between_landscape_and_portrait(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = "eDP-2"
        gui.display_mgr.get_display_rotation.side_effect = ["normal", "normal", "left"]
        gui.display_mgr.set_display_rotation.return_value = True

        with patch.object(Tinta4Plus, "get_display_state", return_value={"mode": "eink"}), \
             patch.object(Tinta4Plus, "_apply_input_mode", return_value=True), \
             patch.object(Tinta4Plus, "save_orientation_preference", return_value=True):
            Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)
            Tinta4Plus.EInkControlGUI.on_orientation_toggled(gui)

        self.assertEqual(gui.orientation_toggle_btn.cget("text"), "Orientation: Portrait")

    def test_toggle_orientation_reapplies_input_mode_on_success(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = "eDP-1"
        gui.display_mgr.get_display_rotation.side_effect = ["normal", "normal", "left"]
        gui.display_mgr.set_display_rotation.return_value = True

        with patch.object(Tinta4Plus, "get_display_state", return_value={"mode": "oled"}), \
             patch.object(Tinta4Plus, "_apply_input_mode", return_value=True) as apply_mode, \
             patch.object(Tinta4Plus, "save_orientation_preference", return_value=True):
            Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)
            Tinta4Plus.EInkControlGUI.on_orientation_toggled(gui)

        apply_mode.assert_called_once_with(gui.logger, "oled")

    def test_toggle_orientation_updates_ui_after_confirming_live_rotation(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = "eDP-1"
        gui.display_mgr.get_display_rotation.side_effect = ["normal", "normal", "left"]
        gui.display_mgr.set_display_rotation.return_value = True

        with patch.object(Tinta4Plus, "get_display_state", return_value={"mode": "oled"}), \
             patch.object(Tinta4Plus, "_apply_input_mode", return_value=True), \
             patch.object(Tinta4Plus, "save_orientation_preference", return_value=True):
            Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)
            Tinta4Plus.EInkControlGUI.on_orientation_toggled(gui)

        gui.display_mgr.get_display_rotation.assert_called_with("eDP-1")
        self.assertEqual(gui.orientation_rotation, "left")

    def test_failed_toggle_keeps_last_confirmed_orientation_label(self):
        gui = self.make_gui()
        gui.display_mgr.get_active_display.return_value = "eDP-1"
        gui.display_mgr.get_display_rotation.return_value = "normal"
        gui.display_mgr.set_display_rotation.return_value = False

        with patch.object(Tinta4Plus, "get_display_state", return_value={"mode": "oled"}), \
             patch.object(Tinta4Plus, "_apply_input_mode", return_value=True), \
             patch.object(Tinta4Plus, "save_orientation_preference", return_value=True):
            Tinta4Plus.EInkControlGUI.sync_orientation_from_display_state(gui)
            Tinta4Plus.EInkControlGUI.on_orientation_toggled(gui)

        self.assertEqual(gui.orientation_toggle_btn.cget("text"), "Orientation: Landscape")


class FrontlightRecoveryTests(unittest.TestCase):
    def make_gui(self, ec_status):
        gui = type("GuiStub", (), {})()
        gui.helper = MagicMock()
        gui.helper.send_command.return_value = {"success": True, "ec_status": ec_status}
        gui.secureboot_label = FakeWidget()
        gui.secureboot_frame = FakeWidget()
        gui.secure_boot_warning = FakeWarningWidget()
        gui.brightness_scale = FakeWidget()
        gui.log_message = MagicMock()
        gui.sync_frontlight_state = MagicMock()
        gui.logger = MagicMock()
        return gui

    def test_check_ec_status_enables_slider_hides_warning_and_syncs_when_available(self):
        gui = self.make_gui({"secure_boot_enabled": False, "available": True})

        Tinta4Plus.EInkControlGUI.check_ec_status(gui)

        self.assertEqual(gui.brightness_scale.cget("state"), "normal")
        self.assertTrue(gui.secure_boot_warning.grid_remove_called)
        gui.sync_frontlight_state.assert_called_once()

    def test_check_ec_status_disables_slider_and_shows_warning_when_unavailable(self):
        gui = self.make_gui({"secure_boot_enabled": False, "available": False, "error_message": "denied"})

        with patch.object(Tinta4Plus.messagebox, "showwarning", MagicMock()):
            Tinta4Plus.EInkControlGUI.check_ec_status(gui)

        self.assertEqual(gui.brightness_scale.cget("state"), "disabled")
        self.assertTrue(gui.secure_boot_warning.grid_called)
        gui.sync_frontlight_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
