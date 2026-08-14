from __future__ import annotations

from typing import Any

import pytest

from physics_lab.devices.serial_temperature import SerialTemperatureDevice


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.sent: list[dict[str, Any]] = []
        self.opened = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def read_json(self) -> dict[str, Any]:
        return next(self.responses)


def test_serial_temperature_handshake_and_samples() -> None:
    transport = FakeTransport(
        [
            {"type": "hello", "device_id": "temp-test", "experiment": "temperature", "protocol": 1},
            {"type": "sample", "index": 0, "temperature": 23.1},
            {"type": "sample", "index": 1, "temperature": 23.4},
            {"type": "done"},
        ]
    )
    device = SerialTemperatureDevice("COM8", transport)
    device.connect()
    samples: list[tuple[int, float]] = []

    values = device.request(
        "collect_temperature",
        {"count": 2},
        lambda index, value: samples.append((index, value)),
    )

    assert values == [23.1, 23.4]
    assert samples == [(0, 23.1), (1, 23.4)]
    assert transport.sent == [
        {"command": "hello", "protocol": 1},
        {"command": "collect_temperature", "count": 2},
    ]


def test_serial_temperature_rejects_wrong_firmware_target() -> None:
    transport = FakeTransport([{"type": "hello", "experiment": "pendulum", "protocol": 1}])
    device = SerialTemperatureDevice("COM8", transport)

    with pytest.raises(RuntimeError, match="not 'temperature'"):
        device.connect()


def test_serial_temperature_rejects_unsupported_protocol() -> None:
    transport = FakeTransport([{"type": "hello", "experiment": "temperature", "protocol": 2}])
    device = SerialTemperatureDevice("COM8", transport)

    with pytest.raises(RuntimeError, match="Unsupported protocol version: 2"):
        device.connect()
