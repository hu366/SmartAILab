from typing import Any

import pytest

from physics_lab.devices.serial_faraday import FaradaySampleTimeout, SerialFaradayDevice


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


def test_serial_faraday_handshake_and_formal_samples() -> None:
    transport = FakeTransport(
        [
            {"type": "hello", "device_id": "faraday-test", "experiment": "faraday", "protocol": 1},
            {"type": "sample", "index": 0, "raw_left": 2, "raw_right": 1, "r": 2, "mode": "formal"},
            {"type": "done", "mode": "formal"},
        ]
    )
    device = SerialFaradayDevice("COM8", 57600, transport)
    device.connect()
    samples = device.request("collect", {"count": 1})
    assert samples[0]["raw_left"] == 2.0
    assert samples[0]["r"] == 2.0
    assert transport.sent == [
        {"command": "hello", "protocol": 1},
        {"command": "collect", "count": 1},
    ]


def test_serial_faraday_rejects_wrong_experiment() -> None:
    device = SerialFaradayDevice("COM8", transport=FakeTransport([{"type": "hello", "experiment": "temperature", "protocol": 1}]))
    with pytest.raises(RuntimeError, match="not 'faraday'"):
        device.connect()


def test_serial_faraday_rejects_unsupported_protocol() -> None:
    device = SerialFaradayDevice("COM8", transport=FakeTransport([{"type": "hello", "experiment": "faraday", "protocol": 2}]))
    with pytest.raises(RuntimeError, match="Unsupported protocol version: 2"):
        device.connect()


def test_serial_faraday_keeps_invalid_sample_and_recovers(monkeypatch) -> None:
    transport = FakeTransport(
        [
            {"type": "hello", "experiment": "faraday", "protocol": 1},
            {
                "type": "sample", "index": 0, "raw_left": 0, "raw_right": 10,
                "r": 0, "valid": False, "reason": "optical_out_of_range",
            },
            {"type": "sample", "index": 0, "raw_left": 20, "raw_right": 10, "r": 2},
            {"type": "done", "mode": "formal"},
        ]
    )
    device = SerialFaradayDevice("COM8", transport=transport)
    device.connect()
    observed = []
    samples = device.request("collect", {"count": 1}, observed.append)

    assert len(samples) == 1
    assert samples[0]["valid"] is True
    assert observed[0]["valid"] is False
    assert observed[0]["reason"].startswith("optical_out_of_range")
    assert observed[1]["valid"] is True


def test_serial_faraday_times_out_after_abnormal_recovery_window(monkeypatch) -> None:
    from physics_lab.devices import serial_faraday

    monkeypatch.setattr(serial_faraday, "SAMPLE_RECOVERY_TIMEOUT_SECONDS", 0.0)
    transport = FakeTransport(
        [
            {"type": "hello", "experiment": "faraday", "protocol": 1},
            {"type": "sample", "index": 0, "raw_left": 0, "raw_right": 10, "r": 0},
        ]
    )
    device = SerialFaradayDevice("COM8", transport=transport)
    device.connect()

    with pytest.raises(FaradaySampleTimeout, match="5秒内"):
        device.request("collect", {"count": 1})
    assert transport.sent[-1] == {"command": "stop"}
