from __future__ import annotations

import math
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from physics_lab.core.cancellation import ExperimentCancelled
from physics_lab.core.contracts import DeviceRequirement, ExperimentProject, PlatformServices, WorkflowWorker
from physics_lab.ui.raw_data_panel import RawDataPanel


class TemperatureConfigPage(QWidget):
    page_id = "plugin-config"
    title = "采集参数"

    def __init__(self, project: ExperimentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.sample_count = QSpinBox()
        self.sample_count.setRange(5, 200)
        self.sample_count.setValue(int(project.plugin_config.get("sample_count", 30)))
        form = QFormLayout()
        form.addRow("采样数量", self.sample_count)
        note = QLabel("温度设备将采集一组温度数据并计算统计结果。")
        note.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("温度采集参数"))
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch()

    def validate(self) -> tuple[bool, str]:
        if self.sample_count.value() < 5:
            return False, "采样数量不能少于 5。"
        return True, ""

    def save_to_project(self, project: ExperimentProject) -> None:
        project.plugin_config["sample_count"] = self.sample_count.value()


class TemperatureRunPage(QWidget):
    page_id = "run"
    title = "采集温度"

    def __init__(self, project: ExperimentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("温度数据采集"))
        note = QLabel("开始后可以暂停、继续或取消本次采集。")
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()


class TemperatureResultPage(QWidget):
    page_id = "result"
    title = "温度结果"

    def __init__(self, project: ExperimentProject, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.repository = repository
        self.content = QLabel()
        self.content.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("结果摘要"))
        layout.addWidget(self.content)
        self.raw_data = RawDataPanel(
            project,
            repository,
            "raw/temperature_samples.jsonl",
            (("index", "序号"), ("temperature", "温度（°C）")),
            self.recalculate,
            self,
        )
        layout.addWidget(self.raw_data)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        result = self.project.result
        self.content.setText(
            f"平均温度：{result.get('average', '--')} °C\n"
            f"最低温度：{result.get('minimum', '--')} °C\n"
            f"最高温度：{result.get('maximum', '--')} °C\n"
            f"采样数量：{result.get('points', '--')}"
        )
        self.raw_data.refresh()

    def recalculate(self) -> None:
        values = self.repository.read_raw_samples(self.project, "raw/temperature_samples.jsonl", "temperature")
        if not values:
            raise ValueError("没有可用的温度数据")
        self.project.result = {
            "average": round(sum(values) / len(values), 3),
            "minimum": round(min(values), 3),
            "maximum": round(max(values), 3),
            "points": len(values),
        }
        self.repository.save(self.project)
        self.refresh()


def run_temperature(
    project: ExperimentProject,
    worker: WorkflowWorker,
    device,
    repository,
) -> None:
    try:
        device.connect()

        def on_sample(index: int, _value: float) -> None:
            if getattr(worker, "is_cancelled", lambda: False)():
                raise ExperimentCancelled()
            if getattr(worker, "is_paused", lambda: False)():
                device.request("pause")
                getattr(worker, "wait_until_resumed", lambda: None)()
                if getattr(worker, "is_cancelled", lambda: False)():
                    raise ExperimentCancelled()
                device.request("resume")
            worker.progress.emit(index, f"正在采集第 {index + 1} 个温度数据")

        count = int(project.plugin_config.get("sample_count", 30))
        values = device.request("collect_temperature", {"count": count}, on_sample=on_sample)
        result = {
            "average": round(sum(values) / len(values), 3),
            "minimum": round(min(values), 3),
            "maximum": round(max(values), 3),
            "points": len(values),
        }
        project.device_metadata = device.metadata
        repository.write_raw_samples(project, values, "temperature_samples.jsonl", "temperature")
        worker.completed.emit(result)
    except ExperimentCancelled:
        worker.cancelled.emit()
    except Exception as exc:  # pragma: no cover - worker boundary
        worker.failed.emit(str(exc))
    finally:
        device.disconnect()


class TemperatureWorkflow:
    def __init__(self, project: ExperimentProject, services: PlatformServices, requirements: tuple[DeviceRequirement, ...]) -> None:
        self.project = project
        self.services = services
        self.requirements = requirements
        self.pages: dict[str, QWidget] = {}

    def page_ids(self) -> list[str]:
        return ["plugin-config", "run", "result"]

    def page_title(self, page_id: str) -> str:
        return {"plugin-config": "采集参数", "run": "采集温度", "result": "温度结果"}[page_id]

    def create_page(self, page_id: str, parent: QWidget | None = None) -> QWidget:
        page_type = {
            "plugin-config": TemperatureConfigPage,
            "run": TemperatureRunPage,
            "result": TemperatureResultPage,
        }[page_id]
        page = (
            page_type(self.project, self.services.project_repository, parent)
            if page_id == "result"
            else page_type(self.project, parent)
        )
        self.pages[page_id] = page
        return page

    def run(self, worker: WorkflowWorker) -> None:
        leases = self.services.device_manager.acquire_all(self.requirements, owner=self.project.project_id)
        try:
            run_temperature(self.project, worker, leases[0].device, self.services.project_repository)
        finally:
            self.services.device_manager.release_all(leases)


class TemperaturePlugin:
    plugin_id = "temperature"
    api_version = 1
    version = "1.0.0"
    display_name = "温度采集实验"
    description = "采集温度数据并计算平均、最大和最小值"
    icon = "°"
    device_requirements = (
        DeviceRequirement(
            "esp32s3_board",
            frozenset({"temperature_sampling"}),
            firmware="temperature-esp32s3-sim",
            channels=frozenset({"temperature_sensor"}),
        ),
    )

    def create_workflow(self, project: ExperimentProject, services: PlatformServices) -> TemperatureWorkflow:
        return TemperatureWorkflow(project, services, self.device_requirements)


def get_plugin() -> TemperaturePlugin:
    return TemperaturePlugin()
