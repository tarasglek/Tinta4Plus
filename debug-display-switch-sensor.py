#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import signal
import struct
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

IIO_ROOT = Path("/sys/bus/iio/devices")
INPUT_DEVICES = Path("/proc/bus/input/devices")

EV_SYN = 0x00
EV_SW = 0x05
SW_TABLET_MODE = 0x01
INPUT_EVENT_STRUCT = struct.Struct("llHHI")


@dataclass(slots=True, frozen=True)
class HingeDevice:
    sysfs: Path
    devnode: Path
    scale: float
    labels: tuple[str, str, str]


@dataclass(slots=True, frozen=True)
class AppConfig:
    logfile: Path
    duration_s: float | None
    poll_interval_s: float
    include_input: bool


def ts() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def find_hinge_device() -> HingeDevice:
    for d in IIO_ROOT.glob("iio:device*"):
        namef = d / "name"
        if not namef.exists() or namef.read_text().strip() != "hinge":
            continue
        scale = float((d / "in_angl_scale").read_text().strip())
        labels = tuple((d / f"in_angl{i}_label").read_text().strip() for i in range(3))
        return HingeDevice(sysfs=d, devnode=Path("/dev") / d.name, scale=scale, labels=labels)  # type: ignore[arg-type]
    raise RuntimeError("No hinge IIO device found")


def find_tablet_mode_event() -> str | None:
    if not INPUT_DEVICES.exists():
        return None
    blocks = INPUT_DEVICES.read_text(errors="ignore").split("\n\n")
    for block in blocks:
        if 'Name="Lenovo Yoga Tablet Mode Control switch"' not in block:
            continue
        handlers_line = next((line for line in block.splitlines() if line.startswith("H: Handlers=")), "")
        if not handlers_line:
            continue
        for token in handlers_line.removeprefix("H: Handlers=").split():
            if token.startswith("event") and token[5:].isdigit():
                return f"/dev/input/{token}"
    return None


def normalize_deg(value: float) -> float:
    wrapped = value % 360.0
    if wrapped > 180.0:
        wrapped -= 360.0
    return wrapped


def decode_input_event(data: bytes) -> tuple[int, int, int]:
    if len(data) != INPUT_EVENT_STRUCT.size:
        raise ValueError(f"short read: {len(data)} < {INPUT_EVENT_STRUCT.size}")
    _, _, event_type, code, value = INPUT_EVENT_STRUCT.unpack(data)
    return event_type, code, int(value)


def format_input_event_detail(event_type: int, code: int, value: int) -> str | None:
    if event_type == EV_SYN:
        return None
    if event_type == EV_SW and code == SW_TABLET_MODE:
        state = "tablet" if value else "laptop"
        return f"SW_TABLET_MODE value={value} state={state}"
    return f"event type=0x{event_type:02x} code=0x{code:02x} value={value}"


class CsvSink:
    def __init__(self, f: TextIO) -> None:
        self._writer = csv.writer(f)
        self._writer.writerow([
            "timestamp",
            "source",
            "raw0",
            "raw1",
            "raw2",
            "deg0",
            "deg1",
            "deg2",
            "detail",
        ])

    def row(self, values: list[str]) -> None:
        self._writer.writerow(values)


class HingeSampler:
    def __init__(self, dev: HingeDevice, sink: CsvSink) -> None:
        self.dev = dev
        self.sink = sink
        self._last: tuple[int, int, int] | None = None

    def _read_raw(self) -> tuple[int, int, int]:
        return tuple(int((self.dev.sysfs / f"in_angl{i}_raw").read_text().strip()) for i in range(3))  # type: ignore[return-value]

    def _emit(self, raws: tuple[int, int, int], detail: str) -> None:
        if raws == self._last:
            return
        deg = tuple(normalize_deg(v * self.dev.scale * 57.29577951308232) for v in raws)
        t = ts()
        self.sink.row([
            t,
            "iio",
            str(raws[0]),
            str(raws[1]),
            str(raws[2]),
            f"{deg[0]:.2f}",
            f"{deg[1]:.2f}",
            f"{deg[2]:.2f}",
            detail,
        ])
        print(f"{t} IIO {self.dev.labels[0]}={deg[0]:6.2f}° {self.dev.labels[1]}={deg[1]:6.2f}° {self.dev.labels[2]}={deg[2]:6.2f}°")
        self._last = raws

    async def run(self, poll_interval_s: float) -> None:
        # Best effort event-driven wakeup via /dev/iio:* read.
        # Some kernels return EINVAL here; we gracefully fall back to polling.
        try:
            fd = os.open(self.dev.devnode, os.O_RDONLY)
            try:
                while True:
                    await asyncio.to_thread(os.read, fd, 20)  # block until sample-ish wakeup
                    self._emit(self._read_raw(), "triggered")
            finally:
                os.close(fd)
        except OSError as exc:
            print(f"{ts()} WARN iio event-read unavailable ({exc}); fallback poll={poll_interval_s}s", file=sys.stderr)
            while True:
                self._emit(self._read_raw(), "poll")
                await asyncio.sleep(poll_interval_s)


async def input_task(sink: CsvSink, devnode: str) -> None:
    fd = os.open(devnode, os.O_RDONLY)
    try:
        while True:
            data = await asyncio.to_thread(os.read, fd, INPUT_EVENT_STRUCT.size)
            if not data:
                await asyncio.sleep(0.01)
                continue
            while len(data) < INPUT_EVENT_STRUCT.size:
                chunk = await asyncio.to_thread(os.read, fd, INPUT_EVENT_STRUCT.size - len(data))
                if not chunk:
                    break
                data += chunk
            if len(data) != INPUT_EVENT_STRUCT.size:
                continue

            event_type, code, value = decode_input_event(data)
            detail = format_input_event_detail(event_type, code, value)
            if detail is None:
                continue

            t = ts()
            sink.row([t, "input", "", "", "", "", "", "", detail])
            print(f"{t} INPUT {detail}")
    finally:
        os.close(fd)


async def main_async(cfg: AppConfig) -> int:
    hinge = find_hinge_device()
    tablet_input = find_tablet_mode_event() if cfg.include_input else None

    cfg.logfile.parent.mkdir(parents=True, exist_ok=True)
    with cfg.logfile.open("w", newline="", encoding="utf-8") as f:
        sink = CsvSink(f)
        print(f"hinge={hinge.sysfs} dev={hinge.devnode} logfile={cfg.logfile}")
        if tablet_input:
            print(f"input={tablet_input}")
        elif cfg.include_input:
            print("input=not-found")

        tasks = [asyncio.create_task(HingeSampler(hinge, sink).run(cfg.poll_interval_s))]
        if tablet_input and os.access(tablet_input, os.R_OK):
            tasks.append(asyncio.create_task(input_task(sink, tablet_input)))
        elif cfg.include_input:
            print(f"{ts()} WARN input stream unavailable (need read access to tablet switch event node)", file=sys.stderr)

        try:
            if cfg.duration_s is None:
                await asyncio.gather(*tasks)
            else:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=cfg.duration_s)
        except asyncio.TimeoutError:
            print(f"{ts()} done (duration reached)")
        except asyncio.CancelledError:
            pass
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return 0


def parse_args() -> AppConfig:
    p = argparse.ArgumentParser(description="Debug display switch sensors (hinge + tablet mode)")
    p.add_argument("logfile", nargs="?", default=f"/tmp/hinge-correlate-{datetime.now():%Y%m%d-%H%M%S}.csv")
    p.add_argument("--duration", type=float, default=None, help="Auto-stop after N seconds")
    p.add_argument("--poll-interval", type=float, default=0.05, help="Fallback poll interval in seconds")
    p.add_argument("--no-input", action="store_true", help="Disable input event stream")
    a = p.parse_args()
    return AppConfig(
        logfile=Path(a.logfile),
        duration_s=a.duration,
        poll_interval_s=a.poll_interval,
        include_input=not a.no_input,
    )


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, lambda: [t.cancel() for t in asyncio.all_tasks(loop)])
        except NotImplementedError:
            pass


def main() -> int:
    cfg = parse_args()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        return loop.run_until_complete(main_async(cfg))
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
