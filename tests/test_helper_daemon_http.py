import json
import unittest
from unittest.mock import Mock

from HelperDaemon import HelperDaemon


class HelperDaemonHTTPTests(unittest.TestCase):
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
