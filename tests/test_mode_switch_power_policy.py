import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import mode_switch


XSET_OUTPUT = """
Keyboard Control:
  auto repeat:  on    key click percent:  0    LED mask:  00000000
Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  300    cycle:  300
DPMS (Energy Star):
  Standby: 120    Suspend: 0    Off: 600
  DPMS is Enabled
"""


class DisplayPowerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()

    def _completed(self, stdout=""):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    def test_capture_display_power_state_includes_xset_screensaver_and_dpms(self):
        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd, ["xset", "q"])
            return self._completed(XSET_OUTPUT)

        with patch.object(mode_switch.subprocess, "run", side_effect=fake_run):
            state = mode_switch._capture_display_power_state(self.logger)

        self.assertEqual(
            state["xset"],
            {
                "screensaver_timeout": 300,
                "screensaver_cycle": 300,
                "dpms_enabled": True,
                "dpms_standby": 120,
                "dpms_suspend": 0,
                "dpms_off": 600,
            },
        )

    def test_disable_for_eink_saves_once_and_disables_xset_and_xfce_blanking(self):
        saved_settings = {}
        xfce_values = {
            "/xfce4-power-manager/dpms-enabled": "true\n",
            "/xfce4-power-manager/blank-on-ac": "10\n",
            "/xfce4-power-manager/blank-on-battery": "1\n",
            "/xfce4-power-manager/dpms-on-ac-sleep": "2\n",
            "/xfce4-power-manager/dpms-on-ac-off": "10\n",
            "/xfce4-power-manager/pre-blank-command": "/home/taras/Documents/info-display/run.sh\n",
        }
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if cmd == ["xset", "q"]:
                return self._completed(XSET_OUTPUT)
            if cmd[:4] == ["xfconf-query", "-c", "xfce4-power-manager", "-p"] and len(cmd) == 4 + 1:
                return self._completed(xfce_values[cmd[4]])
            return self._completed("")

        def fake_save(_logger, settings):
            saved_settings.clear()
            saved_settings.update(settings)
            return True

        with patch.object(mode_switch, "_load_settings", return_value={}), \
             patch.object(mode_switch, "_save_settings", side_effect=fake_save), \
             patch.object(mode_switch.subprocess, "run", side_effect=fake_run):
            mode_switch._disable_dpms_for_eink(self.logger)

        self.assertIn("display_power_saved_state", saved_settings)
        self.assertEqual(saved_settings["display_power_saved_state"]["xset"]["screensaver_timeout"], 300)
        self.assertEqual(
            saved_settings["display_power_saved_state"]["xfce_power_manager"]["/xfce4-power-manager/blank-on-ac"],
            {"type": "int", "value": 10},
        )
        self.assertIn(["xset", "s", "off"], commands)
        self.assertIn(["xset", "-dpms"], commands)
        self.assertIn([
            "xfconf-query", "-c", "xfce4-power-manager", "-p",
            "/xfce4-power-manager/dpms-enabled", "-s", "false",
        ], commands)
        self.assertIn([
            "xfconf-query", "-c", "xfce4-power-manager", "-p",
            "/xfce4-power-manager/blank-on-ac", "-s", "0",
        ], commands)
        self.assertIn([
            "xfconf-query", "-c", "xfce4-power-manager", "-p",
            "/xfce4-power-manager/blank-on-battery", "-s", "0",
        ], commands)

    def test_disable_for_eink_does_not_overwrite_existing_oled_snapshot(self):
        existing_snapshot = {
            "xset": {"screensaver_timeout": 111},
            "xfce_power_manager": {},
        }
        saved = []

        with patch.object(mode_switch, "_load_settings", return_value={"display_power_saved_state": existing_snapshot}), \
             patch.object(mode_switch, "_save_settings", side_effect=lambda logger, settings: saved.append(settings) or True), \
             patch.object(mode_switch.subprocess, "run", return_value=self._completed("")):
            mode_switch._disable_dpms_for_eink(self.logger)

        self.assertEqual(saved, [])

    def test_restore_after_eink_restores_xset_and_xfce_then_clears_snapshot(self):
        snapshot = {
            "xset": {
                "screensaver_timeout": 300,
                "screensaver_cycle": 300,
                "dpms_enabled": True,
                "dpms_standby": 120,
                "dpms_suspend": 0,
                "dpms_off": 600,
            },
            "xfce_power_manager": {
                "/xfce4-power-manager/dpms-enabled": {"type": "bool", "value": True},
                "/xfce4-power-manager/blank-on-ac": {"type": "int", "value": 10},
                "/xfce4-power-manager/pre-blank-command": {
                    "type": "string",
                    "value": "/home/taras/Documents/info-display/run.sh",
                },
            },
        }
        settings = {"display_power_saved_state": snapshot, "orientation_preference": "left"}
        saved_settings = []
        commands = []

        def fake_save(_logger, new_settings):
            saved_settings.append(dict(new_settings))
            return True

        with patch.object(mode_switch, "_load_settings", return_value=settings), \
             patch.object(mode_switch, "_save_settings", side_effect=fake_save), \
             patch.object(mode_switch.subprocess, "run", side_effect=lambda cmd, **kwargs: commands.append(cmd) or self._completed("")):
            mode_switch._restore_dpms_after_eink(self.logger)

        self.assertIn(["xset", "s", "300", "300"], commands)
        self.assertIn(["xset", "+dpms"], commands)
        self.assertIn(["xset", "dpms", "120", "0", "600"], commands)
        self.assertIn([
            "xfconf-query", "-c", "xfce4-power-manager", "-p",
            "/xfce4-power-manager/dpms-enabled", "-s", "true",
        ], commands)
        self.assertIn([
            "xfconf-query", "-c", "xfce4-power-manager", "-p",
            "/xfce4-power-manager/blank-on-ac", "-s", "10",
        ], commands)
        self.assertEqual(saved_settings[-1], {"orientation_preference": "left"})

    def test_restore_accepts_legacy_dpms_snapshot(self):
        legacy = {"enabled": False, "standby": 12, "suspend": 0, "off": 34}
        settings = {"dpms_saved_state": legacy}
        commands = []
        saved_settings = []

        with patch.object(mode_switch, "_load_settings", return_value=settings), \
             patch.object(mode_switch, "_save_settings", side_effect=lambda logger, new_settings: saved_settings.append(dict(new_settings)) or True), \
             patch.object(mode_switch.subprocess, "run", side_effect=lambda cmd, **kwargs: commands.append(cmd) or self._completed("")):
            mode_switch._restore_dpms_after_eink(self.logger)

        self.assertIn(["xset", "-dpms"], commands)
        self.assertEqual(saved_settings[-1], {})


if __name__ == "__main__":
    unittest.main()
