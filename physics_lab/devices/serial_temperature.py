from __future__ import annotations

import time
from typing import Any, Callable

from physics_lab.devices.protocol import CURRENT_PROTOCOL_VERSION, validate_protocol_version
from physics_lab.devices.serial_transport import SerialTransport


class TemperatureDeviceCompatibilityError(RuntimeError):
    """The connected board is reachable but cannot run the temperature experiment."""


class SerialTemperatureDevice:
    device_type = "esp32s3_board"
    capabilities = frozenset({"temperature_sampling"})
    firmware = ""
    protocol_version = CURRENT_PROTOCOL_VERSION
    channels = frozenset({"temperature_sensor"})

    def __init__(self, port: str, transport: SerialTransport | None = None) -> None:
        self.port = port
        self.device_id = f"serial:{port}"
        self.transport = transport or SerialTransport(port)
        self.connected = False
        self.identity: dict[str, Any] = {"transport": "serial", "port": port}

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
                self.transport.send_json({"command": "hello", "protocol": CURRENT_PROTOCOL_VERSION})
                response = self.transport.read_json()
                if response.get("type") != "hello":
                    raise TemperatureDeviceCompatibilityError(
                        f"Unexpected device handshake response: {response}"
                    )
                if response.get("experiment") != "temperature":
                    raise TemperatureDeviceCompatibilityError(
                        f"Device is for '{response.get('experiment')}', not 'temperature'"
                    )
                try:
                    protocol_version = validate_protocol_version(response.get("protocol"))
                except ValueError as exc:
                    raise TemperatureDeviceCompatibilityError(str(exc)) from exc
                self.identity.update(response)
                self.device_id = str(response.get("device_id", self.device_id))
                self.firmware = str(response.get("firmware", ""))
                self.protocol_version = protocol_version
                self.connected = True
                return
            except TemperatureDeviceCompatibilityError:
                self.connected = False
                self.transport.close()
                raise
            except Exception as exc:
                last_error = exc
                self.connected = False
                self.transport.close()
                if attempt + 1 < attempts:
                    time.sleep(retry_delay)
        raise ConnectionError(f"Unable to connect to temperature device on {self.port}: {last_error}") from last_error

    def reconnect(self, attempts: int = 3, retry_delay: float = 0.5) -> None:
        self.disconnect()
        self.connect(attempts=attempts, retry_delay=retry_delay)

    def disconnect(self) -> None:
        self.connected = False
        self.transport.close()

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        on_sample: Callable[[int, float], None] | None = None,
    ) -> list[float]:
        if not self.connected:
            raise RuntimeError("Temperature device is not connected")
        self.transport.send_json({"command": command, **(payload or {})})
        if command != "collect_temperature":
            return []

        values: list[float] = []
        while True:
            message = self.transport.read_json()
            message_type = message.get("type")
            if message_type == "sample":
                index = int(message["index"])
                value = float(message["temperature"])
                values.append(value)
                if on_sample is not None:
                    try:
                        on_sample(index, value)
                    except Exception:
                        try:
                            self.transport.send_json({"command": "stop"})
                        except Exception:
                            pass
                        raise
            elif message_type == "done":
                return values
            elif message_type == "error":
                raise RuntimeError(str(message.get("message", "Unknown device error")))
