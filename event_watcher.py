"""Background event watcher helpers for lid + RandR invalidations."""

from __future__ import annotations

import subprocess
import time


LID_STATE_PATHS = (
    "/proc/acpi/button/lid/LID0/state",
    "/proc/acpi/button/lid/LID/state",
)


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


def _read_lid_state():
    for path in LID_STATE_PATHS:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read().lower()
            if "closed" in text:
                return True
            if "open" in text:
                return False
        except FileNotFoundError:
            continue
        except Exception:
            return None
    return None


def _randr_fingerprint():
    try:
        output = subprocess.run(
            ["xrandr", "--query"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except Exception:
        return None

    connected_lines = []
    for line in output.splitlines():
        if " connected" in line:
            connected_lines.append(" ".join(line.split()))
    return "\n".join(sorted(connected_lines))


def watch_events(send_conn):
    """Watch lid and display changes and emit invalidations on one channel."""

    send_message = send_conn.send
    last_lid_state = _read_lid_state()
    last_randr = _randr_fingerprint()

    try:
        while True:
            time.sleep(0.5)

            lid_state = _read_lid_state()
            if lid_state is not None and lid_state != last_lid_state:
                last_lid_state = lid_state
                send_lid_invalidation(send_message)

            randr = _randr_fingerprint()
            if randr is not None and randr != last_randr:
                last_randr = randr
                send_randr_invalidation(send_message)
    except KeyboardInterrupt:
        return
    except Exception as exc:
        send_error(send_message, exc)
