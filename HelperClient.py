"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software.
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

import http.client
import json
import socket
import threading
import time


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=10.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


class HelperClient:
    """Client for communicating with privileged helper daemon via HTTP over Unix socket"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [0.5, 1.0, 2.0]

    ROUTES = {
        "enable-eink": ("POST", "/v1/eink/enable", lambda params: {}),
        "disable-eink": ("POST", "/v1/eink/disable", lambda params: {}),
        "refresh-eink": ("POST", "/v1/eink/refresh", lambda params: {}),
        "set-dynamic": ("POST", "/v1/eink/mode/dynamic", lambda params: {}),
        "set-reading": ("POST", "/v1/eink/mode/reading", lambda params: {}),
        "get-ec-status": ("GET", "/v1/ec/status", lambda params: None),
        "get-frontlight-state": ("GET", "/v1/frontlight", lambda params: None),
        "enable-frontlight": ("POST", "/v1/frontlight/enable", lambda params: {"brightness_level": params["brightness_level"]} if "brightness_level" in params else {}),
        "disable-frontlight": ("POST", "/v1/frontlight/disable", lambda params: {}),
        "set-brightness": ("POST", "/v1/frontlight/brightness", lambda params: {"level": params.get("level")}),
    }

    def __init__(self, logger):
        self.logger = logger
        self.connected = False
        self.lock = threading.Lock()
        self.socket_path = None
        self.last_error = None
        self.socket = None

    def connect(self, socket_path, timeout=10.0):
        self.socket_path = socket_path

        for attempt in range(self.MAX_RETRIES):
            try:
                self._close_socket()
                probe = UnixSocketHTTPConnection(socket_path, timeout=timeout)
                probe.connect()
                self.socket = probe.sock
                probe.close()
                self.socket = None

                self.connected = True
                self.last_error = None
                self.logger.info(f"Connected to helper daemon at {socket_path}")
                return True
            except Exception as e:
                self.last_error = str(e)
                self.logger.warning(f"Connection attempt {attempt + 1}/{self.MAX_RETRIES} failed: {e}")
                self._close_socket()
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAYS[attempt])

        self.connected = False
        return False

    def disconnect(self):
        with self.lock:
            self._close_socket()
            self.connected = False
            self.socket_path = None
            self.logger.info("Disconnected from helper daemon")

    def _route_for(self, command, params):
        if command not in self.ROUTES:
            raise ValueError(f"Unknown command: {command}")
        method, path, body_fn = self.ROUTES[command]
        body_obj = body_fn(params)
        return method, path, body_obj

    def send_command(self, command, **params):
        if not self.connected or not self.socket_path:
            raise RuntimeError(f"Not connected to helper daemon. Last error: {self.last_error}")

        with self.lock:
            try:
                method, path, body_obj = self._route_for(command, params)
                body = None
                headers = {"Accept": "application/json"}
                if body_obj is not None:
                    body = json.dumps(body_obj).encode("utf-8")
                    headers["Content-Type"] = "application/json"

                conn = UnixSocketHTTPConnection(self.socket_path, timeout=10.0)
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                raw = response.read()
                conn.close()

                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if response.status >= 400:
                    self.last_error = payload.get("error", f"HTTP {response.status}")
                    raise RuntimeError(self.last_error)

                return payload

            except (socket.timeout, socket.error, OSError) as e:
                self.connected = False
                self.last_error = str(e)
                self.logger.error(f"Socket/HTTP error during '{command}': {e}")
                raise RuntimeError(f"Socket error: {e}")
            except Exception as e:
                self.connected = False
                self.last_error = str(e)
                self.logger.error(f"Command '{command}' error: {e}")
                raise

    def _close_socket(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def is_connected(self):
        return self.connected and bool(self.socket_path)

    def get_last_error(self):
        return self.last_error
