from __future__ import annotations

import time
import math
from threading import Lock
from typing import Any, Callable

from physics_lab.devices.protocol import CURRENT_PROTOCOL_VERSION, validate_protocol_version
from physics_lab.devices.serial_transport import SerialTransport


class FaradayDeviceCompatibilityError(RuntimeError):
    """The connected board cannot run the Faraday experiment."""


class FaradaySampleTimeout(TimeoutError):
    """No valid Faraday sample arrived within the recovery window."""


ADC_MIN_VALUE = 0.0
ADC_MAX_VALUE = 4095.0
SAMPLE_RECOVERY_TIMEOUT_SECONDS = 5.0


class SerialFaradayDevice:
    device_type = "esp32s3_board"
    capabilities = frozenset({"faraday_sampling"})
    firmware = ""
    protocol_version = CURRENT_PROTOCOL_VERSION
    channels = frozenset({"raw_left", "raw_right"})

    def __init__(self, port: str, baudrate: int = 115200, transport: SerialTransport | None = None) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.device_id = f"serial:faraday:{port}:{self.baudrate}"
        self.transport = transport or SerialTransport(port, baudrate=self.baudrate)
        self.connected = False
        self.identity: dict[str, Any] = {"transport": "serial", "port": port, "baudrate": self.baudrate}
        self._send_lock = Lock()

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "channels": sorted(self.channels),
            **self.identity,
        }

    def connect(self, attempts: int = 3, retry_delay: float = 0.5) -> None:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                self.transport.open()
                self.send_command("hello", {"protocol": CURRENT_PROTOCOL_VERSION})
                response = self.transport.read_json()
                if response.get("type") != "hello":
                    raise FaradayDeviceCompatibilityError(f"Unexpected device handshake response: {response}")
                if response.get("experiment") != "faraday":
                    raise FaradayDeviceCompatibilityError(
                        f"Device is for '{response.get('experiment')}', not 'faraday'"
                    )
                try:
                    protocol_version = validate_protocol_version(response.get("protocol"))
                except ValueError as exc:
                    raise FaradayDeviceCompatibilityError(str(exc)) from exc
                self.identity.update({key: value for key, value in response.items() if key != "device_id"})
                self.identity["hardware_device_id"] = str(response.get("device_id", self.device_id))
                self.firmware = str(response.get("firmware", ""))
                self.protocol_version = protocol_version
                self.connected = True
                return
            except FaradayDeviceCompatibilityError:
                self.connected = False
                self.transport.close()
                raise
            except Exception as exc:
                last_error = exc
                self.connected = False
                self.transport.close()
                if attempt + 1 < attempts:
                    time.sleep(retry_delay)
        raise ConnectionError(f"Unable to connect to Faraday device on {self.port}: {last_error}") from last_error

    def disconnect(self) -> None:
        self.connected = False
        self.transport.close()

    def send_command(self, command: str, payload: dict[str, Any] | None = None) -> None:
        with self._send_lock:
            self.transport.send_json({"command": command, **(payload or {})})

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        on_sample: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("Faraday device is not connected")
        self.send_command(command, payload)
        if command not in {"debug_start", "collect"}:
            return []

        samples: list[dict[str, Any]] = []
        no_sample_deadline = time.monotonic() + SAMPLE_RECOVERY_TIMEOUT_SECONDS
        abnormal_deadline: float | None = None
        while True:
            try:
                message = self.transport.read_json()
            except TimeoutError as exc:
                deadline = abnormal_deadline or no_sample_deadline
                if time.monotonic() >= deadline:
                    self._stop_stream()
                    raise FaradaySampleTimeout(
                        f"5秒内没有恢复正常光路数据（{command}）"
                    ) from exc
                continue
            message_type = message.get("type")
            if message_type == "sample":
                sample = self._parse_sample(message)
                if on_sample is not None:
                    on_sample(sample)
                if not sample["valid"]:
                    if abnormal_deadline is None:
                        abnormal_deadline = time.monotonic() + SAMPLE_RECOVERY_TIMEOUT_SECONDS
                    if time.monotonic() >= abnormal_deadline:
                        self._stop_stream()
                        raise FaradaySampleTimeout(
                            f"5秒内没有恢复正常光路数据（{sample['reason']}）"
                        )
                    continue
                abnormal_deadline = None
                no_sample_deadline = time.monotonic() + SAMPLE_RECOVERY_TIMEOUT_SECONDS
                samples.append(sample)
            elif message_type == "done":
                return samples
            elif message_type == "error":
                raise RuntimeError(str(message.get("message", "Unknown device error")))
            else:
                raise ValueError(f"Unexpected Faraday device message: {message}")

    @staticmethod
    def _parse_sample(message: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []

        try:
            index = int(message.get("index", -1))
        except (TypeError, ValueError):
            index = -1
            reasons.append("index无效")

        def parse_value(key: str) -> float | None:
            try:
                value = float(message[key])
            except (KeyError, TypeError, ValueError):
                reasons.append(f"{key}无效")
                return None
            if not math.isfinite(value):
                reasons.append(f"{key}不是有限值")
                return None
            return value

        raw_left = parse_value("raw_left")
        raw_right = parse_value("raw_right")
        raw_ratio = message.get("r")
        try:
            ratio = float(raw_ratio) if raw_ratio is not None else None
        except (TypeError, ValueError):
            ratio = None
            reasons.append("r无效")

        if raw_left is not None and not ADC_MIN_VALUE < raw_left <= ADC_MAX_VALUE:
            reasons.append("左路超出有效范围")
        if raw_right is not None and not ADC_MIN_VALUE < raw_right <= ADC_MAX_VALUE:
            reasons.append("右路超出有效范围")
        if ratio is None and raw_left is not None and raw_right not in (None, 0.0):
            ratio = raw_left / raw_right
        if ratio is None or not math.isfinite(ratio) or ratio <= 0:
            reasons.append("R无效")

        if message.get("valid") is False:
            reasons.insert(0, str(message.get("reason", "设备标记为异常")))

        # Keep the raw values even for an invalid event so the result can be
        # traced back to the exact optical reading that was rejected.
        return {
            "index": index,
            "raw_left": raw_left,
            "raw_right": raw_right,
            "r": ratio,
            "mode": str(message.get("mode", "formal")),
            "valid": not reasons,
            "reason": "; ".join(dict.fromkeys(reasons)),
        }

    def _stop_stream(self) -> None:
        """Stop a timed-out stream and consume its terminal message."""
        try:
            self.send_command("stop")
        except Exception:
            return
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                if self.transport.read_json().get("type") == "done":
                    return
            except Exception:
                return
