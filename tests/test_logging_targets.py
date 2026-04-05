import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import HelperDaemon
import Tinta4Plus


class LoggingTargetsTests(unittest.TestCase):
    def test_tinta_setup_logger_writes_to_helper_log_file(self):
        with patch.object(Tinta4Plus.logging, "FileHandler") as file_handler_cls:
            logger = Tinta4Plus.setup_logger()

        file_handler_cls.assert_called_once_with("/tmp/TintaHelper.log", mode="a")
        self.assertEqual(logger.name, "tinta4plus-gui")

    def test_toggle_setup_logger_writes_to_helper_log_file(self):
        toggle_path = Path(__file__).resolve().parents[1] / "toggle-eink.py"
        spec = importlib.util.spec_from_file_location("toggle_eink_module", toggle_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with patch.object(module.logging, "FileHandler") as file_handler_cls:
            logger = module.setup_logger()

        file_handler_cls.assert_called_once_with("/tmp/TintaHelper.log", mode="a")
        self.assertEqual(logger.name, "toggle-eink")

    def test_helper_main_uses_append_mode_for_helper_log_file(self):
        with patch.object(HelperDaemon.os, "geteuid", return_value=0), \
             patch.object(HelperDaemon.logging, "FileHandler") as file_handler_cls, \
             patch.object(HelperDaemon.logging, "getLogger") as get_logger, \
             patch.object(HelperDaemon, "HelperDaemon") as daemon_cls:
            get_logger.return_value = unittest.mock.MagicMock()
            daemon_cls.return_value.run.return_value = 0
            rc = HelperDaemon.main()

        self.assertEqual(rc, 0)
        file_handler_cls.assert_called_once_with("/tmp/TintaHelper.log", mode="a")


if __name__ == "__main__":
    unittest.main()
