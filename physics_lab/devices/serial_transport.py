from __future__ import annotations

import json
from typing import Any

import serial


class SerialTransport:
    """Newline-delimited JSON transport for Arduino-compatible boards."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        if self.is_open:
            return
        self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
        self._serial = None

    def send_json(self, message: dict[str, Any]) -> None:
        if not self.is_open:
            raise RuntimeError("Serial transport is not open")
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._serial.write(raw.encode("utf-8"))
        self._serial.flush()

    def read_json(self) -> dict[str, Any]:
        if not self.is_open:
            raise RuntimeError("Serial transport is not open")
        raw = self._serial.readline()
        if not raw:
            raise TimeoutError(f"Timed out waiting for data from {self.port}")
        try:
            message = json.loads(raw.decode("utf-8").strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON from {self.port}: {raw!r}") from exc
        if not isinstance(message, dict):
            raise ValueError(f"Expected a JSON object from {self.port}")
        return message

