from __future__ import annotations

from PySide6.QtWidgets import QWidget

from physics_lab.core.contracts import DeviceRequirement, ExperimentProject, PlatformServices, WorkflowWorker
from physics_lab.plugins.faraday.config_page import FaradayConfigPage
from physics_lab.plugins.faraday.controller import FaradayController
from physics_lab.plugins.faraday.operation_page import FaradayOperationPage
from physics_lab.plugins.faraday.result_page import FaradayResultPage


class FaradayWorkflow:
    def __init__(self, project: ExperimentProject, services: PlatformServices, requirements: tuple[DeviceRequirement, ...]) -> None:
        self.project = project
        self.services = services
        self.requirements = requirements
        self.pages: dict[str, QWidget] = {}
        self.controller = FaradayController(project, services)

    def page_ids(self) -> list[str]:
        return ["plugin-config", "run", "result"]

    def page_title(self, page_id: str) -> str:
        return {"plugin-config": "实验参数", "run": "实验采集", "result": "实验分析"}[page_id]

    def create_page(self, page_id: str, parent: QWidget | None = None) -> QWidget:
        if page_id == "plugin-config":
            page = FaradayConfigPage(
                self.project,
                parent,
                repository=self.services.project_repository,
            )
        elif page_id == "run":
            page = FaradayOperationPage(self.project, self.controller, parent)
        elif page_id == "result":
            page = FaradayResultPage(self.project, self.services.project_repository, parent)
        else:
            raise KeyError(page_id)
        self.pages[page_id] = page
        return page

    def run(self, worker: WorkflowWorker) -> None:
        self.controller.run(worker)


class FaradayPlugin:
    plugin_id = "faraday"
    api_version = 1
    version = "1.0.0"
    display_name = "法拉第磁光效应实验"
    description = "测量旋光角并计算不同波长下的维尔德常数"
    icon = "∠"
    device_requirements = (
        DeviceRequirement(
            "esp32s3_board",
            frozenset({"faraday_sampling"}),
            firmware="faraday-esp32s3-zero",
            channels=frozenset({"raw_left", "raw_right"}),
        ),
    )

    def create_workflow(self, project: ExperimentProject, services: PlatformServices) -> FaradayWorkflow:
        return FaradayWorkflow(project, services, self.device_requirements)


def get_plugin() -> FaradayPlugin:
    return FaradayPlugin()
