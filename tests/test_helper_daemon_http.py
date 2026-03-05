import json
import unittest
from unittest.mock import Mock

from HelperDaemon import HelperDaemon


class HelperDaemonHTTPTests(unittest.TestCase):
    def test_set_brightness_level_zero_disables_frontlight(self):
        logger = Mock()
        daemon = HelperDaemon(logger)
        daemon.ec = Mock()
        daemon.ec.access_available = True
        daemon.ec.disable_frontlight.return_value = (True, 0x05)

        payload = daemon.handle_command({"command": "set-brightness", "params": {"level": 0}})

        self.assertTrue(payload["success"])
        daemon.ec.disable_frontlight.assert_called_once_with()
        daemon.ec.set_brightness.assert_not_called()

    def test_set_brightness_positive_enables_then_sets_brightness(self):
        logger = Mock()
        daemon = HelperDaemon(logger)
        daemon.ec = Mock()
        daemon.ec.access_available = True
        daemon.ec.enable_frontlight.return_value = (True, 0x06)
        daemon.ec.set_brightness.return_value = (True, 0x04)

        payload = daemon.handle_command({"command": "set-brightness", "params": {"level": 1}})

        self.assertTrue(payload["success"])
        daemon.ec.enable_frontlight.assert_called_once_with()
        daemon.ec.set_brightness.assert_called_once_with(1)

    def test_post_v1_eink_refresh_maps_to_refresh_command(self):
        logger = Mock()
        daemon = HelperDaemon(logger)
        daemon.handle_command = lambda cmd: {"success": True, "echo": cmd["command"]}

        status, payload = daemon.handle_http_request("POST", "/v1/eink/refresh", b"{}")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"success": True, "echo": "refresh-eink"})

    def test_invalid_json_returns_400(self):
        logger = Mock()
        daemon = HelperDaemon(logger)

        status, payload = daemon.handle_http_request("POST", "/v1/eink/refresh", b"{")

        self.assertEqual(status, 400)
        self.assertFalse(payload["success"])
        self.assertIn("Invalid JSON", payload["error"])

    def test_unknown_route_returns_404(self):
        logger = Mock()
        daemon = HelperDaemon(logger)

        status, payload = daemon.handle_http_request("POST", "/v1/nope", b"{}")

        self.assertEqual(status, 404)
        self.assertFalse(payload["success"])

    def test_wrong_method_returns_405(self):
        logger = Mock()
        daemon = HelperDaemon(logger)

        status, payload = daemon.handle_http_request("GET", "/v1/eink/refresh", b"")

        self.assertEqual(status, 405)
        self.assertFalse(payload["success"])

    def test_access_log_includes_method_path_status_and_ms(self):
        logger = Mock()
        daemon = HelperDaemon(logger)
        daemon.handle_command = lambda cmd: {"success": True}

        daemon.handle_http_request("POST", "/v1/eink/refresh", b"{}")

        log_messages = "\n".join(str(c.args[0]) for c in logger.info.call_args_list)
        self.assertIn('HTTP unix-client "POST /v1/eink/refresh" 200', log_messages)
        self.assertIn("ms", log_messages)


if __name__ == "__main__":
    unittest.main()
