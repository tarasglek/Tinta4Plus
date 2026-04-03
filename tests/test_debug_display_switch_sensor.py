import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "debug-display-switch-sensor.py"


spec = importlib.util.spec_from_file_location("debug_display_switch_sensor", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class DebugDisplaySwitchSensorTests(unittest.TestCase):
    def test_find_tablet_mode_event_parses_handlers_line(self):
        sample = '''I: Bus=0019 Vendor=0000 Product=0000 Version=0000
N: Name="Lenovo Yoga Tablet Mode Control switch"
P: Phys=06129D99-6083-4164-81AD-F092F9D773A6/input0
S: Sysfs=/devices/platform/PNP0C14:01/wmi_bus/wmi_bus-PNP0C14:01/06129D99-6083-4164-81AD-F092F9D773A6/input/input25
U: Uniq=
H: Handlers=event14
B: PROP=0
B: EV=21
B: SW=2
'''
        with tempfile.TemporaryDirectory() as td:
            input_devices = Path(td) / "devices"
            input_devices.write_text(sample, encoding="utf-8")
            original = module.INPUT_DEVICES
            module.INPUT_DEVICES = input_devices
            try:
                self.assertEqual(module.find_tablet_mode_event(), "/dev/input/event14")
            finally:
                module.INPUT_DEVICES = original

    def test_normalize_deg_wraps_above_180(self):
        self.assertEqual(module.normalize_deg(353.0), -7.0)
        self.assertEqual(module.normalize_deg(180.0), 180.0)
        self.assertEqual(module.normalize_deg(90.0), 90.0)
        self.assertEqual(module.normalize_deg(360.0), 0.0)

    def test_decode_input_event_extracts_type_code_value(self):
        packed = struct.pack(
            module.INPUT_EVENT_STRUCT.format,
            0,
            0,
            module.EV_SW,
            module.SW_TABLET_MODE,
            1,
        )
        event_type, code, value = module.decode_input_event(packed)
        self.assertEqual((event_type, code, value), (module.EV_SW, module.SW_TABLET_MODE, 1))

    def test_format_input_event_detail_filters_syn(self):
        self.assertIsNone(module.format_input_event_detail(module.EV_SYN, 0, 0))

    def test_format_input_event_detail_formats_tablet_mode(self):
        self.assertEqual(
            module.format_input_event_detail(module.EV_SW, module.SW_TABLET_MODE, 1),
            "SW_TABLET_MODE value=1 state=tablet",
        )


if __name__ == "__main__":
    unittest.main()
