import json
import unittest
from unittest.mock import Mock, patch

from HelperClient import HelperClient


class FakeHTTPResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload or {"success": True}

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class FakeHTTPConnection:
    last_request = None
    response = FakeHTTPResponse()

    def __init__(self, socket_path, timeout=10.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def request(self, method, url, body=None, headers=None):
        FakeHTTPConnection.last_request = {
            "method": method,
            "url": url,
            "body": body,
            "headers": headers or {},
        }

    def getresponse(self):
        return FakeHTTPConnection.response

    def close(self):
        pass


class HTTPUnixSocketClientTests(unittest.TestCase):
    @patch("HelperClient.UnixSocketHTTPConnection", FakeHTTPConnection)
    def test_refresh_eink_maps_to_post_v1_eink_refresh(self):
        logger = Mock()
        client = HelperClient(logger)
        client.connected = True
        client.socket_path = "/run/tinta4plus.sock"
        client.socket = object()

        FakeHTTPConnection.response = FakeHTTPResponse(status=200, payload={"success": True, "message": "ok"})
        result = client.send_command("refresh-eink")

        self.assertTrue(result["success"])
        req = FakeHTTPConnection.last_request
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "/v1/eink/refresh")
        self.assertEqual(json.loads(req["body"].decode("utf-8")), {})
        self.assertEqual(req["headers"].get("Content-Type"), "application/json")

    @patch("HelperClient.UnixSocketHTTPConnection", FakeHTTPConnection)
    def test_set_brightness_uses_v1_frontlight_brightness_payload(self):
        logger = Mock()
        client = HelperClient(logger)
        client.connected = True
        client.socket_path = "/run/tinta4plus.sock"
        client.socket = object()

        FakeHTTPConnection.response = FakeHTTPResponse(status=200, payload={"success": True})
        client.send_command("set-brightness", level=80)

        req = FakeHTTPConnection.last_request
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "/v1/frontlight/brightness")
        self.assertEqual(json.loads(req["body"].decode("utf-8")), {"level": 80})

    @patch("HelperClient.UnixSocketHTTPConnection", FakeHTTPConnection)
    def test_non_200_response_raises_runtime_error(self):
        logger = Mock()
        client = HelperClient(logger)
        client.connected = True
        client.socket_path = "/run/tinta4plus.sock"
        client.socket = object()

        FakeHTTPConnection.response = FakeHTTPResponse(status=404, payload={"success": False, "error": "not found"})

        with self.assertRaises(RuntimeError):
            client.send_command("refresh-eink")


if __name__ == "__main__":
    unittest.main()
