from __future__ import annotations

import math
import time
from typing import Any, Callable


class SimulatedPendulumDevice:
    device_id = "simulated-pendulum-01"
    device_type = "esp32s3_board"
    capabilities = frozenset({"period_sampling"})
    firmware = "pendulum-esp32s3-sim"
    protocol_version = 1
    channels = frozenset({"period_sensor"})

    def __init__(self) -> None:
        self.connected = False
        self.paused = False

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "transport": "simulated",
            "firmware": self.firmware,
            "protocol": self.protocol_version,
            "channels": sorted(self.channels),
        }

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.paused = False

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        on_sample: Callable[[int, float], None] | None = None,
    ) -> list[float]:
        if not self.connected:
            raise RuntimeError("Pendulum device is not connected")
        if command == "pause":
            self.paused = True
            return []
        if command == "resume":
            self.paused = False
            return []
        if command != "collect_periods":
            raise ValueError(f"Unsupported simulated command: {command}")
        count = int((payload or {}).get("count", 101))
        values: list[float] = []
        for index in range(count):
            while self.paused:
                time.sleep(0.01)
            time.sleep(0.018)
            value = 2.0 + 0.18 * math.sin(index / 8)
            values.append(value)
            if on_sample is not None:
                on_sample(index, value)
        return values


class SimulatedTemperatureDevice:
    device_id = "simulated-temperature-01"
    device_type = "esp32s3_board"
    capabilities = frozenset({"temperature_sampling"})
    firmware = "temperature-esp32s3-sim"
    protocol_version = 1
    channels = frozenset({"temperature_sensor"})

    def __init__(self) -> None:
        self.connected = False
        self.paused = False

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "transport": "simulated",
            "firmware": self.firmware,
            "protocol": self.protocol_version,
            "channels": sorted(self.channels),
        }

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.paused = False

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        on_sample: Callable[[int, float], None] | None = None,
    ) -> list[float]:
        if not self.connected:
            raise RuntimeError("Temperature device is not connected")
        if command == "pause":
            self.paused = True
            return []
        if command == "resume":
            self.paused = False
            return []
        if command != "collect_temperature":
            raise ValueError(f"Unsupported simulated command: {command}")
        count = int((payload or {}).get("count", 30))
        values: list[float] = []
        for index in range(count):
            while self.paused:
                time.sleep(0.01)
            time.sleep(0.03)
            value = 23.5 + 1.8 * math.sin(index / 4)
            values.append(value)
            if on_sample is not None:
                on_sample(index, value)
        return values
