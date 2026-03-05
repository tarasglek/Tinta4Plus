import json
import socket
import struct
import threading
import unittest
from unittest.mock import Mock

from HelperClient import HelperClient
from HelperDaemon import HelperDaemon


class FakeSocket:
    def __init__(self, response_bytes):
        self.response_bytes = response_bytes
        self.sent = b""

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        if not self.response_bytes:
            return b""
        chunk = self.response_bytes[:n]
        self.response_bytes = self.response_bytes[n:]
        return chunk


class UnixSocketProtocolTests(unittest.TestCase):
    def test_helper_client_send_command_uses_length_prefixed_json_protocol(self):
        logger = Mock()
        client = HelperClient(logger)

        response = {"success": True, "message": "ok"}
        response_json = json.dumps(response).encode("utf-8")
        fake_sock = FakeSocket(struct.pack("!I", len(response_json)) + response_json)

        client.socket = fake_sock
        client.connected = True

        result = client.send_command("refresh-eink", mode="full")

        self.assertEqual(result, response)

        sent_length = struct.unpack("!I", fake_sock.sent[:4])[0]
        sent_payload = fake_sock.sent[4:]
        self.assertEqual(sent_length, len(sent_payload))

        sent_json = json.loads(sent_payload.decode("utf-8"))
        self.assertEqual(sent_json["command"], "refresh-eink")
        self.assertEqual(sent_json["params"], {"mode": "full"})

    def test_helper_daemon_send_response_uses_length_prefix(self):
        logger = Mock()
        daemon = HelperDaemon(logger)

        server_sock, client_sock = socket.socketpair()
        try:
            daemon._send_response(server_sock, {"success": True, "value": 123})

            length_data = client_sock.recv(4)
            self.assertEqual(len(length_data), 4)
            response_len = struct.unpack("!I", length_data)[0]

            payload = b""
            while len(payload) < response_len:
                payload += client_sock.recv(response_len - len(payload))

            parsed = json.loads(payload.decode("utf-8"))
            self.assertEqual(parsed, {"success": True, "value": 123})
        finally:
            server_sock.close()
            client_sock.close()

    def test_helper_daemon_handle_client_processes_length_prefixed_command(self):
        logger = Mock()
        daemon = HelperDaemon(logger)
        daemon.running = True
        daemon.handle_command = lambda cmd: {"success": True, "echo": cmd["command"]}

        server_sock, client_sock = socket.socketpair()

        def run_handler():
            daemon.handle_client(server_sock)

        t = threading.Thread(target=run_handler, daemon=True)
        t.start()

        try:
            command = {"command": "set-reading", "params": {}}
            payload = json.dumps(command).encode("utf-8")
            client_sock.sendall(struct.pack("!I", len(payload)) + payload)

            response_len_data = client_sock.recv(4)
            self.assertEqual(len(response_len_data), 4)
            response_len = struct.unpack("!I", response_len_data)[0]

            response_payload = b""
            while len(response_payload) < response_len:
                response_payload += client_sock.recv(response_len - len(response_payload))

            response = json.loads(response_payload.decode("utf-8"))
            self.assertEqual(response, {"success": True, "echo": "set-reading"})
        finally:
            daemon.running = False
            client_sock.close()
            t.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
