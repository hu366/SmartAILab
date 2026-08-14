from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget


@dataclass
class GeneralConfig:
    name: str
    number: str
    experiment_date: str


@dataclass
class ExperimentProject:
    project_id: str
    plugin_id: str
    plugin_version: str
    general: GeneralConfig
    status: str = "draft"
    current_step: str = "plugin-config"
    plugin_config: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    device_metadata: dict[str, Any] = field(default_factory=dict)
    raw_artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass(frozen=True)
class DeviceRequirement:
    device_type: str
    capabilities: frozenset[str] = frozenset()
    firmware: str | None = None
    channels: frozenset[str] = frozenset()


class Device(Protocol):
    device_id: str
    device_type: str
    capabilities: frozenset[str]
    firmware: str
    protocol_version: int
    channels: frozenset[str]

    @property
    def metadata(self) -> dict[str, Any]:
        ...

    def connect(self) -> None:
        ...

    def disconnect(self) -> None:
        ...

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        on_sample: Callable[[int, float], None] | None = None,
    ) -> Any:
        ...


@dataclass(frozen=True)
class PlatformServices:
    device_manager: "DeviceManager"
    project_repository: "ProjectRepository"


class ExperimentPlugin(Protocol):
    plugin_id: str
    version: str
    display_name: str
    description: str
    icon: str
    device_requirements: tuple[DeviceRequirement, ...]

    def create_workflow(self, project: ExperimentProject, services: PlatformServices) -> "ExperimentWorkflow":
        ...


class WorkflowPage(Protocol):
    page_id: str
    title: str

    def validate(self) -> tuple[bool, str]:
        ...

    def save_to_project(self, project: ExperimentProject) -> None:
        ...


class ExperimentWorkflow(Protocol):
    def page_ids(self) -> list[str]:
        ...

    def create_page(self, page_id: str, parent: QWidget | None = None) -> QWidget:
        ...

    def page_title(self, page_id: str) -> str:
        ...

    def run(self, worker: WorkflowWorker) -> None:
        ...


class WorkflowWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()


# Imported only for type checking; the runtime module uses the contracts above.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from physics_lab.core.device_manager import DeviceManager
    from physics_lab.core.project_repository import ProjectRepository


def today_string() -> str:
    return date.today().isoformat()
