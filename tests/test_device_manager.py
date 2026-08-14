import pytest

from physics_lab.core.contracts import DeviceRequirement
from physics_lab.core.device_manager import DeviceManager
from physics_lab.core.simulated_devices import SimulatedPendulumDevice


def test_device_manager_matches_capabilities_and_exclusive_leases() -> None:
    manager = DeviceManager()
    device = SimulatedPendulumDevice()
    manager.register(device)
    requirement = DeviceRequirement(
        "esp32s3_board",
        frozenset({"period_sampling"}),
        firmware="pendulum-esp32s3-sim",
        channels=frozenset({"period_sensor"}),
    )

    lease = manager.acquire(requirement, owner="project-1")
    assert lease.device is device
    with pytest.raises(LookupError):
        manager.acquire(requirement, owner="project-2")

    manager.release(lease)
    second_lease = manager.acquire(requirement, owner="project-2")
    assert second_lease.device is device


def test_device_manager_acquires_multiple_distinct_devices_atomically() -> None:
    manager = DeviceManager()
    first = SimulatedPendulumDevice()
    second = SimulatedPendulumDevice()
    second.device_id = "simulated-pendulum-02"
    manager.register(first)
    manager.register(second)
    requirement = DeviceRequirement(
        "esp32s3_board",
        frozenset({"period_sampling"}),
        firmware="pendulum-esp32s3-sim",
        channels=frozenset({"period_sensor"}),
    )

    leases = manager.acquire_all((requirement, requirement), owner="project-multi")

    assert {lease.device.device_id for lease in leases} == {
        "simulated-pendulum-01",
        "simulated-pendulum-02",
    }
    manager.release_all(leases)
    assert manager.acquire(requirement, owner="project-next").device is first
