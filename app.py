from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from physics_lab.core.plugin_manager import PluginManager
from physics_lab.core.project_repository import ProjectRepository
from physics_lab.core.contracts import PlatformServices
from physics_lab.core.device_manager import DeviceManager
from physics_lab.core.simulated_devices import SimulatedPendulumDevice, SimulatedTemperatureDevice
from physics_lab.devices.serial_pendulum import SerialPendulumDevice
from physics_lab.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Physics Lab")
    app.setOrganizationName("SmartAILab")

    root = Path(__file__).parent
    repository = ProjectRepository(root / "projects")
    plugin_manager = PluginManager(root / "physics_lab" / "plugins")
    plugin_manager.discover()
    device_manager = DeviceManager()
    serial_port = os.environ.get("PHYSICS_LAB_PENDULUM_PORT", "").strip()
    if serial_port:
        device_manager.register(SerialPendulumDevice(serial_port))
    else:
        device_manager.register(SimulatedPendulumDevice())
    device_manager.register(SimulatedTemperatureDevice())
    services = PlatformServices(device_manager, repository)

    window = MainWindow(repository, plugin_manager, services)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
