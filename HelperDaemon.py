#!/usr/bin/env python3
"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.
"""

import json
import logging
import os
import signal
import socket
import sys
import time
import atexit
from http.server import BaseHTTPRequestHandler, HTTPServer

from ECController import ECController
from EInkUSBController import EInkUSBController

SOCKET_PATH = '/run/tinta4plus.sock'
PID_FILE = '/tmp/tinta4plus.pid'
LOG_LEVEL = logging.DEBUG
SYSTEMD_FIRST_FD = 3


class HelperHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "Tinta4PlusHelper/1.0"

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b''
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    def _send_json(self, status, payload):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method):
        start = time.time()
        status, payload = self.server.daemon.handle_http_request(method, self.path, self._read_raw_body_if_needed(method))
        self._send_json(status, payload)
        elapsed_ms = (time.time() - start) * 1000
        self.server.daemon.logger.info(
            f'HTTP unix-client "{method} {self.path}" {status} {elapsed_ms:.1f}ms'
        )

    def _read_raw_body_if_needed(self, method):
        if method != 'POST':
            return b''
        length = int(self.headers.get('Content-Length', '0'))
        return self.rfile.read(length) if length > 0 else b''

    def do_POST(self):
        self._dispatch('POST')

    def do_GET(self):
        self._dispatch('GET')

    def log_message(self, fmt, *args):
        return


class ActivatedUnixHTTPServer(HTTPServer):
    address_family = socket.AF_UNIX

    def __init__(self, sock, daemon):
        self.daemon = daemon
        super().__init__(server_address=SOCKET_PATH, RequestHandlerClass=HelperHTTPRequestHandler, bind_and_activate=False)
        self.socket = sock
        self.server_address = SOCKET_PATH

    def server_bind(self):
        return

    def server_activate(self):
        return


class HelperDaemon:
    def __init__(self, logger):
        self.logger = logger
        self.running = False
        self.socket_path = SOCKET_PATH
        self.pid_file = PID_FILE
        self.server_socket = None
        self.http_server = None
        self.eink = None
        self.ec = None

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self.shutdown)

    def _signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down")
        self.shutdown()

    def _create_pid_file(self):
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"Created PID file: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Failed to create PID file: {e}")

    def _remove_pid_file(self):
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                self.logger.info("Removed PID file")
        except Exception as e:
            self.logger.warning(f"Failed to remove PID file: {e}")

    def _create_socket(self):
        listen_pid = os.environ.get('LISTEN_PID')
        listen_fds = int(os.environ.get('LISTEN_FDS', '0'))
        if not (listen_pid and int(listen_pid) == os.getpid() and listen_fds >= 1):
            raise RuntimeError("Systemd socket activation not available (LISTEN_FDS/LISTEN_PID missing)")
        self.server_socket = socket.socket(fileno=SYSTEMD_FIRST_FD)
        self.logger.info(f"Using systemd-activated socket FD {SYSTEMD_FIRST_FD}")

    def _remove_socket(self):
        try:
            if self.http_server:
                self.http_server.server_close()
                self.http_server = None
            elif self.server_socket:
                self.server_socket.close()
            self.logger.info("Removed socket")
        except Exception as e:
            self.logger.warning(f"Failed to remove socket: {e}")

    def initialize_hardware(self):
        try:
            self.logger.info("Initializing EC controller")
            self.ec = ECController(self.logger)
            ec_status = self.ec.get_access_status()
            if not ec_status['available']:
                self.logger.warning(f"EC access not available: {ec_status['error_message']}")

            self.logger.info("Initializing E-Ink USB controller")
            self.eink = EInkUSBController(self.logger)
            self.eink.connect()
            self.logger.info("Hardware initialization complete")
            return True
        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False

    def cleanup_hardware(self):
        if self.eink:
            self.eink.disconnect()
        self.logger.info("Hardware cleanup complete")

    def _set_frontlight_response(self, response, success, readback, success_msg, failure_msg):
        response['success'] = success
        response['readback'] = f"0x{readback:02x}"
        response['message'] = success_msg if success else failure_msg

    def handle_command(self, command_data):
        try:
            cmd = command_data.get('command')
            params = command_data.get('params', {})
            response = {'success': False, 'error': None}

            if cmd == 'enable-eink':
                self.eink.enable_eink(); response['success'] = True; response['message'] = 'E-Ink display enabled'
            elif cmd == 'disable-eink':
                self.eink.disable_eink(); response['success'] = True; response['message'] = 'E-Ink display disabled'
            elif cmd == 'refresh-eink':
                self.eink.refresh_full(); response['success'] = True; response['message'] = 'E-Ink full refresh completed'
            elif cmd == 'set-dynamic':
                self.eink.set_dynamic_mode(); response['success'] = True; response['message'] = 'E-Ink set to Dynamic Mode (fast refresh)'
            elif cmd == 'set-reading':
                self.eink.set_reading_mode(); response['success'] = True; response['message'] = 'E-Ink set to Reading Mode (high-quality refresh)'
            elif cmd == 'get-ec-status':
                status = self.ec.get_access_status(); response['success'] = True; response['ec_status'] = status; response['message'] = 'EC status retrieved'
            elif cmd == 'get-frontlight-state':
                if not self.ec.access_available: raise RuntimeError(self.ec.error_message or "EC access not available")
                enabled = self.ec.get_frontlight_state(); brightness = self.ec.read_brightness()
                response['success'] = True; response['frontlight_enabled'] = enabled; response['brightness_level'] = brightness; response['message'] = 'Frontlight state retrieved'
            elif cmd == 'enable-frontlight':
                if not self.ec.access_available: raise RuntimeError(self.ec.error_message or "EC access not available")
                brightness_level = params.get('brightness_level')
                success, readback = self.ec.enable_frontlight(brightness_level=brightness_level)
                self._set_frontlight_response(
                    response,
                    success,
                    readback,
                    'Frontlight enabled',
                    'Frontlight enable failed (readback mismatch)',
                )
            elif cmd == 'disable-frontlight':
                if not self.ec.access_available: raise RuntimeError(self.ec.error_message or "EC access not available")
                success, readback = self.ec.disable_frontlight()
                self._set_frontlight_response(
                    response,
                    success,
                    readback,
                    'Frontlight disabled',
                    'Frontlight disable failed (readback mismatch)',
                )
            elif cmd == 'set-brightness':
                if not self.ec.access_available: raise RuntimeError(self.ec.error_message or "EC access not available")
                level = params.get('level')
                if level is None: raise ValueError("Missing 'level' parameter")

                level = int(level)
                response['level'] = level
                if level == 0:
                    success, readback = self.ec.disable_frontlight()
                    self._set_frontlight_response(
                        response,
                        success,
                        readback,
                        'Frontlight disabled via brightness level 0',
                        'Frontlight disable failed (readback mismatch)',
                    )
                else:
                    enable_success, _ = self.ec.enable_frontlight()
                    if not enable_success:
                        response['success'] = False
                        response['error'] = 'Failed to enable frontlight before setting brightness'
                    else:
                        success, readback = self.ec.set_brightness(level)
                        self._set_frontlight_response(
                            response,
                            success,
                            readback,
                            f'Brightness set to {level}',
                            f'Brightness set failed (readback mismatch)',
                        )
            else:
                raise ValueError(f"Unknown command: {cmd}")
            return response
        except Exception as e:
            self.logger.error(f"Command error: {e}")
            return {'success': False, 'error': str(e)}

    def handle_http_request(self, method, path, body_bytes):
        start = time.time()
        route_map = {
            ('POST', '/v1/eink/enable'): ('enable-eink', {}),
            ('POST', '/v1/eink/disable'): ('disable-eink', {}),
            ('POST', '/v1/eink/refresh'): ('refresh-eink', {}),
            ('POST', '/v1/eink/mode/dynamic'): ('set-dynamic', {}),
            ('POST', '/v1/eink/mode/reading'): ('set-reading', {}),
            ('GET', '/v1/ec/status'): ('get-ec-status', {}),
            ('GET', '/v1/frontlight'): ('get-frontlight-state', {}),
            ('POST', '/v1/frontlight/enable'): ('enable-frontlight', 'body'),
            ('POST', '/v1/frontlight/disable'): ('disable-frontlight', {}),
            ('POST', '/v1/frontlight/brightness'): ('set-brightness', 'body'),
        }

        all_paths = {p for _, p in route_map.keys()}
        if path not in all_paths:
            status, payload = 404, {'success': False, 'error': 'Not found'}
            self._log_access(method, path, status, start)
            return status, payload

        key = (method, path)
        if key not in route_map:
            status, payload = 405, {'success': False, 'error': 'Method not allowed'}
            self._log_access(method, path, status, start)
            return status, payload

        try:
            parsed_body = {}
            if body_bytes:
                parsed_body = json.loads(body_bytes.decode('utf-8'))
                if not isinstance(parsed_body, dict):
                    raise ValueError('JSON body must be an object')
        except Exception as e:
            status, payload = 400, {'success': False, 'error': f'Invalid JSON: {e}'}
            self._log_access(method, path, status, start)
            return status, payload

        cmd, params_mode = route_map[key]
        params = parsed_body if params_mode == 'body' else {}
        payload = self.handle_command({'command': cmd, 'params': params})
        status = 200
        self._log_access(method, path, status, start)
        return status, payload

    def _log_access(self, method, path, status, start):
        elapsed_ms = (time.time() - start) * 1000
        self.logger.info(f'HTTP unix-client "{method} {path}" {status} {elapsed_ms:.1f}ms')

    def run(self):
        try:
            if os.path.exists(self.pid_file):
                self.logger.warning(f"PID file exists: {self.pid_file}")
                try:
                    with open(self.pid_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    os.kill(old_pid, 0)
                    self.logger.error(f"Helper already running (PID {old_pid})")
                    return 1
                except (OSError, ValueError):
                    self.logger.info("Stale PID file, removing")
                    os.remove(self.pid_file)

            self._create_pid_file()
            if not self.initialize_hardware():
                self.logger.error("Failed to initialize hardware")
                return 1

            self._create_socket()
            self.running = True
            self.http_server = ActivatedUnixHTTPServer(self.server_socket, self)
            self.logger.info("Helper daemon started (HTTP), waiting for connections")
            self.http_server.serve_forever(poll_interval=0.5)
            return 0
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return 1
        finally:
            self.shutdown()

    def shutdown(self):
        was_running = self.running
        self.running = False
        if was_running:
            self.logger.info("Shutting down...")

        try:
            if self.http_server:
                self.http_server.shutdown()
        except Exception:
            pass

        try:
            self.cleanup_hardware()
        except Exception as e:
            self.logger.warning(f"Hardware cleanup failed: {e}")

        self._remove_socket()
        self._remove_pid_file()
        self.logger.info("Shutdown complete")


def main():
    if os.geteuid() != 0:
        print("ERROR: This helper must be run as root (use pkexec or sudo)", file=sys.stderr)
        return 1

    log_handlers = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/tmp/TintaHelper.log', mode='a')
    ]
    logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=log_handlers)
    logger = logging.getLogger('tinta4plus-helper')

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    logger.info("ThinkBook E-Ink Helper starting")
    daemon = HelperDaemon(logger)
    return daemon.run()


if __name__ == '__main__':
    sys.exit(main())
