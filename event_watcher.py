"""Background event watcher helpers for lid + RandR invalidations."""

from __future__ import annotations

import time


def _safe_send(send_message, payload):
    try:
        send_message(payload)
    except Exception:
        # Parent may have exited.
        pass


def send_lid_invalidation(send_message):
    _safe_send(send_message, ("lid", None))


def send_randr_invalidation(send_message):
    _safe_send(send_message, ("randr", None))


def send_error(send_message, message):
    _safe_send(send_message, ("error", str(message)))


def watch_events(send_conn):
    """Process entrypoint.

    Real lid/RandR subscriptions will push invalidations through this single channel.
    For now this loop keeps the worker process alive until the parent terminates it.
    """

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        return
    except Exception as exc:
        send_error(send_conn.send, exc)
