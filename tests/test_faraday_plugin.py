from pathlib import Path

from PySide6.QtWidgets import QApplication

from physics_lab.core.contracts import GeneralConfig, PlatformServices
from physics_lab.core.device_manager import DeviceManager
from physics_lab.core.plugin_manager import PluginManager
from physics_lab.core.project_repository import ProjectRepository
from physics_lab.plugins.faraday.config_page import FaradayConfigPage
from physics_lab.plugins.faraday.controller import FaradayController
from physics_lab.plugins.faraday.operation_page import FaradayOperationPage


def _qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_faraday_plugin_is_discovered_with_required_channels() -> None:
    manager = PluginManager(Path(__file__).parents[1] / "physics_lab" / "plugins")
    manager.discover()
    plugin = manager.get("faraday")
    assert plugin.display_name == "法拉第磁光效应实验"
    assert plugin.device_requirements[0].capabilities == frozenset({"faraday_sampling"})
    assert plugin.device_requirements[0].channels == frozenset({"raw_left", "raw_right"})


def test_faraday_config_rejects_duplicate_experiment_number(tmp_path: Path) -> None:
    _qt_app()
    repository = ProjectRepository(tmp_path / "projects")
    repository.create("pendulum", "1.0.0", GeneralConfig("已存在", "2026-001", "2026-08-14"))
    project = repository.create("faraday", "1.0.0", GeneralConfig("当前实验", "2026-002", "2026-08-14"))
    page = FaradayConfigPage(project, repository=repository)
    page.sample_name.setText("样品")
    page.sample_material.setText("玻璃")
    page.port.setText("COM16")
    page.experiment_number.setText("2026-001")

    valid, message = page.validate()

    assert not valid
    assert message == "实验编号“2026-001”已存在，请使用其他编号。"


def test_faraday_config_allows_current_experiment_number(tmp_path: Path) -> None:
    _qt_app()
    repository = ProjectRepository(tmp_path / "projects")
    project = repository.create("faraday", "1.0.0", GeneralConfig("当前实验", "2026-001", "2026-08-14"))
    page = FaradayConfigPage(project, repository=repository)
    page.sample_name.setText("样品")
    page.sample_material.setText("玻璃")
    page.port.setText("COM16")

    valid, message = page.validate()

    assert valid, message


def test_faraday_operation_refresh_preserves_measured_points(tmp_path: Path) -> None:
    _qt_app()
    repository = ProjectRepository(tmp_path / "projects")
    project = repository.create("faraday", "1.0.0", GeneralConfig("法拉第", "2026-003", "2026-08-14"))
    project.plugin_config = {
        "wavelengths": [{"id": "wavelength-1", "value_nm": 500.0}],
        "field_points": [
            {"id": "point-1", "current_a": 0.0, "magnetic_field_t": 0.0},
            {"id": "point-2", "current_a": 0.5, "magnetic_field_t": 0.001},
        ],
        "serial": {"samples_per_point": 2},
    }
    controller = FaradayController(project, PlatformServices(DeviceManager(), repository))
    controller._data = {
        "wavelength-1": {
            "points": [
                {"index": 1, "r": 1.0, "theta_rad": 0.0, "status": "complete"},
                {"index": 2, "r": 1.25, "theta_rad": 0.12, "status": "complete"},
            ]
        }
    }
    page = FaradayOperationPage(project, controller)
    page._current_wavelength = "wavelength-1"

    page.refresh_configuration()

    assert page.points.item(1, 3).text() == "1.25"
    assert page.points.item(1, 4).text() == "0.12"
    assert page.points.item(1, 5).text() == "完成"
    assert page.points.item(1, 2).text() == "1"
