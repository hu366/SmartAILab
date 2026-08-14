from __future__ import annotations

import math
from typing import Any, Callable

from physics_lab.core.contracts import ExperimentProject, WorkflowWorker
from physics_lab.core.contracts import Device
from physics_lab.core.cancellation import ExperimentCancelled


def run_pendulum(
    project: ExperimentProject,
    worker: WorkflowWorker,
    device: Device,
    before_complete: Callable[[list[float], dict[str, Any]], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    is_paused: Callable[[], bool] | None = None,
    wait_until_resumed: Callable[[], None] | None = None,
) -> list[float]:
    values: list[float] = []
    try:
        if is_cancelled is not None and is_cancelled():
            raise ExperimentCancelled()
        device.connect()

        def on_sample(index: int, _value: float) -> None:
            if is_cancelled is not None and is_cancelled():
                raise ExperimentCancelled()
            if is_paused is not None and is_paused():
                device.request("pause")
                if wait_until_resumed is not None:
                    wait_until_resumed()
                if is_cancelled is not None and is_cancelled():
                    raise ExperimentCancelled()
                device.request("resume")
            worker.progress.emit(index, f"正在采集第 {index + 1}/101 个数据点")

        values = device.request("collect_periods", {"count": 101}, on_sample=on_sample)
        length = float(project.plugin_config.get("length", 1.0))
        period = sum(values) / len(values)
        gravity = 4 * math.pi**2 * length / (period**2)
        project.device_metadata = device.metadata
        result = {"period": round(period, 4), "gravity": round(gravity, 4), "points": len(values)}
        if before_complete is not None:
            before_complete(values, result)
        worker.completed.emit(result)
        return values
    except ExperimentCancelled:
        worker.cancelled.emit()
        return []
    except Exception as exc:  # pragma: no cover - defensive boundary for worker threads
        worker.failed.emit(str(exc))
        return []
    finally:
        device.disconnect()
