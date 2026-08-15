import math
from threading import Event, Thread

from PySide6.QtCore import Qt

from physics_lab.core.contracts import ExperimentProject, GeneralConfig, PlatformServices, WorkflowWorker
from physics_lab.core.device_manager import DeviceManager
from physics_lab.core.project_repository import ProjectRepository
from physics_lab.plugins.faraday.controller import FaradayController


class FakeFaradayDevice:
    device_type = "esp32s3_board"
    capabilities = frozenset({"faraday_sampling"})
    firmware = ""
    protocol_version = 1
    channels = frozenset({"raw_left", "raw_right"})
    device_id = "fake-faraday"

    def __init__(self, _port: str, _baudrate: int) -> None:
        self.connected = False

    @property
    def metadata(self):
        return {"device_id": self.device_id, "transport": "fake"}

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def send_command(self, _command: str, _payload=None) -> None:
        return None

    def request(self, command, payload=None, on_sample=None):
        if command == "debug_start":
            return []
        count = int((payload or {}).get("count", 1))
        ratio = 1.0 if self._point_index == 0 else math.tan(math.atan(1.0) + 0.1) ** 2
        samples = [{"index": index, "raw_left": ratio, "raw_right": 1.0, "r": ratio, "mode": "formal"} for index in range(count)]
        self._point_index += 1
        for sample in samples:
            if on_sample:
                on_sample(sample)
        return samples

    _point_index = 0


def test_faraday_controller_completes_session_and_releases_dynamic_device(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("physics_lab.plugins.faraday.controller.SerialFaradayDevice", FakeFaradayDevice)
    repository = ProjectRepository(tmp_path)
    project = ExperimentProject("faraday-1", "faraday", "1.0.0", GeneralConfig("f", "faraday-1", "2026-01-01"))
    project.plugin_config = {
        "sample": {"name": "sample", "material": "glass", "length_m": 0.01},
        "wavelengths": [{"id": "wavelength-1", "value_nm": 500.0}],
        "field_points": [
            {"id": "point-1", "current_a": 0.0, "magnetic_field_t": 0.0},
            {"id": "point-2", "current_a": 1.0, "magnetic_field_t": 1.0},
        ],
        "serial": {"port": "FAKE", "baudrate": 115200, "samples_per_point": 2},
    }
    repository.save(project)
    manager = DeviceManager()
    services = PlatformServices(manager, repository)
    controller = FaradayController(project, services)
    worker = WorkflowWorker()
    completed = []
    failed = []
    finished = Event()
    worker.completed.connect(lambda result: (completed.append(result), finished.set()), Qt.ConnectionType.DirectConnection)
    worker.failed.connect(lambda message: (failed.append(message), finished.set()), Qt.ConnectionType.DirectConnection)

    thread = Thread(target=controller.run, args=(worker,))
    thread.start()
    controller.select_wavelength("wavelength-1")
    controller.collect_point("point-1")
    controller.collect_point("point-2")
    assert finished.wait(3), (failed, controller._data, list(controller._commands))
    thread.join(3)

    assert not failed, failed
    assert completed[0]["complete"] is True
    assert completed[0]["wavelengths"][0]["status"] == "complete"
    assert manager.list_devices() == []
    assert repository.read_raw_rows(project, "raw/faraday_samples.jsonl")


def test_faraday_controller_excludes_anomaly_and_keeps_trace(tmp_path, monkeypatch) -> None:
    class RecoveringFaradayDevice(FakeFaradayDevice):
        def __init__(self, port: str, baudrate: int) -> None:
            super().__init__(port, baudrate)
            self._point_index = 0

        def request(self, command, payload=None, on_sample=None):
            if command == "debug_start":
                return []
            count = int((payload or {}).get("count", 1))
            events = []
            if self._point_index == 0:
                events.append({
                    "index": 0,
                    "raw_left": 0.0,
                    "raw_right": 1.0,
                    "r": 0.0,
                    "valid": False,
                    "reason": "optical_out_of_range",
                    "mode": "formal",
                })
            events.extend(
                {
                    "index": index,
                    "raw_left": 1.0,
                    "raw_right": 1.0,
                    "r": 1.0,
                    "valid": True,
                    "mode": "formal",
                }
                for index in range(count)
            )
            self._point_index += 1
            for sample in events:
                if on_sample:
                    on_sample(sample)
            return [sample for sample in events if sample["valid"]]

    monkeypatch.setattr("physics_lab.plugins.faraday.controller.SerialFaradayDevice", RecoveringFaradayDevice)
    repository = ProjectRepository(tmp_path)
    project = ExperimentProject("faraday-2", "faraday", "1.0.0", GeneralConfig("f", "faraday-2", "2026-01-01"))
    project.plugin_config = {
        "sample": {"name": "sample", "material": "glass", "length_m": 0.01},
        "wavelengths": [{"id": "wavelength-1", "value_nm": 500.0}],
        "field_points": [
            {"id": "point-1", "current_a": 0.0, "magnetic_field_t": 0.0},
            {"id": "point-2", "current_a": 1.0, "magnetic_field_t": 1.0},
        ],
        "serial": {"port": "FAKE", "baudrate": 115200, "samples_per_point": 2},
    }
    repository.save(project)
    manager = DeviceManager()
    services = PlatformServices(manager, repository)
    controller = FaradayController(project, services)
    worker = WorkflowWorker()
    completed = []
    failed = []
    finished = Event()
    worker.completed.connect(lambda result: (completed.append(result), finished.set()), Qt.ConnectionType.DirectConnection)
    worker.failed.connect(lambda message: (failed.append(message), finished.set()), Qt.ConnectionType.DirectConnection)

    thread = Thread(target=controller.run, args=(worker,))
    thread.start()
    controller.select_wavelength("wavelength-1")
    controller.collect_point("point-1")
    controller.collect_point("point-2")
    assert finished.wait(3), (failed, controller._data, list(controller._commands))
    thread.join(3)

    assert not failed, failed
    assert completed[0]["complete"] is True
    anomalies = completed[0]["anomalies"]
    assert len(anomalies) == 1
    assert anomalies[0]["point_index"] == 1
    assert anomalies[0]["valid"] if "valid" in anomalies[0] else True
    rows = repository.read_raw_rows(project, "raw/faraday_samples.jsonl")
    assert sum(1 for row in rows if row["status"] == "abnormal") == 1
    assert sum(1 for row in rows if row["status"] == "valid") == 4
