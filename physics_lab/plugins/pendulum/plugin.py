from __future__ import annotations

import math

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from physics_lab.core.contracts import (
    DeviceRequirement,
    ExperimentProject,
    PlatformServices,
    WorkflowWorker,
)
from physics_lab.core.simulator import run_pendulum
from physics_lab.ui.raw_data_panel import RawDataPanel


class PendulumConfigPage(QWidget):
    page_id = "plugin-config"
    title = "实验参数"

    def __init__(self, project: ExperimentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.length = QDoubleSpinBox()
        self.length.setRange(0.1, 10.0)
        self.length.setDecimals(3)
        self.length.setSuffix(" m")
        self.length.setValue(float(project.plugin_config.get("length", 1.0)))
        form = QFormLayout()
        form.addRow("摆长", self.length)
        note = QLabel("模拟设备将采集 101 个周期数据点，并计算重力加速度。")
        note.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("单摆实验参数"))
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch()

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def save_to_project(self, project: ExperimentProject) -> None:
        self.project = project
        self.project.plugin_config["length"] = self.length.value()


class PendulumRunPage(QWidget):
    page_id = "run"
    title = "实验操作"

    def __init__(self, project: ExperimentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.message = QLabel("准备开始数据采集")
        self.message.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("数据采集"))
        layout.addWidget(self.message)
        layout.addStretch()


class PendulumResultPage(QWidget):
    page_id = "result"
    title = "实验结果"

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
            "raw/period_samples.jsonl",
            (("index", "序号"), ("period", "周期（秒）")),
            self.recalculate,
            self,
        )
        layout.addWidget(self.raw_data)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        result = self.project.result
        self.content.setText(
            f"平均周期：{result.get('period', '--')} s\n"
            f"重力加速度：{result.get('gravity', '--')} m/s²\n"
            f"采集点数：{result.get('points', '--')}"
        )
        self.raw_data.refresh()

    def recalculate(self) -> None:
        values = self.repository.read_raw_samples(self.project, "raw/period_samples.jsonl", "period")
        if not values:
            raise ValueError("没有可用的周期数据")
        length = float(self.project.plugin_config.get("length", 1.0))
        period = sum(values) / len(values)
        self.project.result = {
            "period": round(period, 4),
            "gravity": round(4 * math.pi**2 * length / (period**2), 4),
            "points": len(values),
        }
        self.repository.save(self.project)
        self.refresh()


class PendulumWorkflow:
    def __init__(
        self,
        project: ExperimentProject,
        services: PlatformServices,
        device_requirements: tuple[DeviceRequirement, ...],
    ) -> None:
        self.project = project
        self.services = services
        self.device_requirements = device_requirements
        self.pages: dict[str, QWidget] = {}

    def page_ids(self) -> list[str]:
        return ["plugin-config", "run", "result"]

    def page_title(self, page_id: str) -> str:
        return {"plugin-config": "实验参数", "run": "实验操作", "result": "实验结果"}[page_id]

    def create_page(self, page_id: str, parent: QWidget | None = None) -> QWidget:
        page_type = {"plugin-config": PendulumConfigPage, "run": PendulumRunPage, "result": PendulumResultPage}[page_id]
        page = (
            page_type(self.project, self.services.project_repository, parent)
            if page_id == "result"
            else page_type(self.project, parent)
        )
        self.pages[page_id] = page
        return page

    def run(self, worker: WorkflowWorker) -> None:
        leases = self.services.device_manager.acquire_all(self.device_requirements, owner=self.project.project_id)
        try:
            run_pendulum(
                self.project,
                worker,
                leases[0].device,
                before_complete=lambda samples, _result: self.services.project_repository.write_raw_samples(
                    self.project, samples
                ),
                is_cancelled=getattr(worker, "is_cancelled", None),
                is_paused=getattr(worker, "is_paused", None),
                wait_until_resumed=getattr(worker, "wait_until_resumed", None),
            )
        finally:
            self.services.device_manager.release_all(leases)


class PendulumPlugin:
    plugin_id = "pendulum"
    api_version = 1
    version = "1.0.0"
    display_name = "单摆实验"
    description = "通过测量周期计算重力加速度"
    icon = "◌"
    device_requirements = (
        DeviceRequirement(
            "esp32s3_board",
            frozenset({"period_sampling"}),
            firmware="pendulum-esp32s3-sim",
            channels=frozenset({"period_sensor"}),
        ),
    )

    def create_workflow(self, project: ExperimentProject, services: PlatformServices) -> PendulumWorkflow:
        return PendulumWorkflow(project, services, self.device_requirements)


def get_plugin() -> PendulumPlugin:
    return PendulumPlugin()
