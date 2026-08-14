from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from physics_lab.core.contracts import Device, DeviceRequirement


@dataclass(frozen=True)
class DeviceLease:
    device: Device
    owner: str


class DeviceManager:
    """Registry and exclusive lease manager for experiment devices."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._leases: dict[str, DeviceLease] = {}
        self._lock = RLock()

    def register(self, device: Device) -> None:
        with self._lock:
            if device.device_id in self._devices:
                raise ValueError(f"Duplicate device id: {device.device_id}")
            self._devices[device.device_id] = device

    def list_devices(self) -> list[Device]:
        with self._lock:
            return list(self._devices.values())

    def acquire(self, requirement: DeviceRequirement, owner: str) -> DeviceLease:
        return self.acquire_all((requirement,), owner)[0]

    def acquire_all(self, requirements: tuple[DeviceRequirement, ...], owner: str) -> list[DeviceLease]:
        """Acquire distinct devices for all requirements atomically."""
        with self._lock:
            selected: list[Device] = []
            for requirement in requirements:
                device = next(
                    (
                        candidate
                        for candidate in self._devices.values()
                        if candidate not in selected
                        and candidate.device_type == requirement.device_type
                        and requirement.capabilities.issubset(candidate.capabilities)
                        and (not requirement.firmware or not candidate.firmware or candidate.firmware == requirement.firmware)
                        and requirement.channels.issubset(candidate.channels)
                        and candidate.device_id not in self._leases
                    ),
                    None,
                )
                if device is None:
                    raise LookupError(
                        f"No available device for type '{requirement.device_type}' "
                        f"with capabilities {sorted(requirement.capabilities)}, "
                        f"firmware '{requirement.firmware or '*'}' and channels {sorted(requirement.channels)}"
                    )
                selected.append(device)

            leases = [DeviceLease(device, owner) for device in selected]
            self._leases.update({lease.device.device_id: lease for lease in leases})
            return leases

    def release_all(self, leases: list[DeviceLease]) -> None:
        with self._lock:
            for lease in leases:
                current = self._leases.get(lease.device.device_id)
                if current == lease:
                    del self._leases[lease.device.device_id]

    def release(self, lease: DeviceLease) -> None:
        with self._lock:
            current = self._leases.get(lease.device.device_id)
            if current == lease:
                del self._leases[lease.device.device_id]

    def release_owner(self, owner: str) -> None:
        with self._lock:
            for device_id, lease in list(self._leases.items()):
                if lease.owner == owner:
                    del self._leases[device_id]
