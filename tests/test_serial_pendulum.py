from __future__ import annotations

from typing import Any

import pytest

from physics_lab.devices.serial_pendulum import SerialPendulumDevice


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


class FlakyTransport(FakeTransport):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__(responses)
        self.open_attempts = 0

    def open(self) -> None:
        self.open_attempts += 1
        if self.open_attempts == 1:
            raise OSError("temporary serial failure")
        super().open()


def test_serial_pendulum_handshake_and_samples() -> None:
    transport = FakeTransport(
        [
            {"type": "hello", "device_id": "esp-test", "experiment": "pendulum", "protocol": 1},
            {"type": "sample", "index": 0, "period": 2.0},
            {"type": "sample", "index": 1, "period": 2.1},
            {"type": "done"},
        ]
    )
    device = SerialPendulumDevice("COM7", transport)
    device.connect()
    samples: list[tuple[int, float]] = []
    values = device.request("collect_periods", {"count": 2}, lambda index, value: samples.append((index, value)))

    assert values == [2.0, 2.1]
    assert samples == [(0, 2.0), (1, 2.1)]
    assert transport.sent == [{"command": "hello"}, {"command": "collect_periods", "count": 2}]
    device.disconnect()


def test_serial_pendulum_rejects_wrong_firmware_target() -> None:
    transport = FakeTransport([{"type": "hello", "experiment": "temperature", "protocol": 1}])
    device = SerialPendulumDevice("COM7", transport)
    with pytest.raises(RuntimeError, match="not 'pendulum'"):
        device.connect()


def test_serial_pendulum_retries_handshake() -> None:
    transport = FlakyTransport(
        [{"type": "hello", "device_id": "esp-test", "experiment": "pendulum", "protocol": 1}]
    )
    device = SerialPendulumDevice("COM7", transport)

    device.connect(attempts=2, retry_delay=0)

    assert transport.open_attempts == 2
    assert device.connected
