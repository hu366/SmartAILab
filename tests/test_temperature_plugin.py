from pathlib import Path

from physics_lab.core.contracts import DeviceRequirement
from physics_lab.core.device_manager import DeviceManager
from physics_lab.core.plugin_manager import PluginManager
from physics_lab.core.project_repository import ProjectRepository
from physics_lab.core.simulated_devices import SimulatedTemperatureDevice


def test_temperature_plugin_is_discovered_with_its_device_requirement() -> None:
    manager = PluginManager(Path(__file__).parents[1] / "physics_lab" / "plugins")
    manager.discover()

    plugin = manager.get("temperature")
    assert plugin.display_name == "温度采集实验"
    assert plugin.device_requirements[0].device_type == "esp32s3_board"
    assert plugin.device_requirements[0].channels == frozenset({"temperature_sensor"})


def test_temperature_device_can_be_registered_for_plugin() -> None:
    device_manager = DeviceManager()
    device_manager.register(SimulatedTemperatureDevice())
    lease = device_manager.acquire_all(
        (
            DeviceRequirement(
                "esp32s3_board",
                frozenset({"temperature_sampling"}),
                firmware="temperature-esp32s3-sim",
                channels=frozenset({"temperature_sensor"}),
            ),
        ),
        owner="temperature-test",
    )[0]
    assert lease.device.device_type == "esp32s3_board"
    device_manager.release(lease)
