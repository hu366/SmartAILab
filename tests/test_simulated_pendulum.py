from physics_lab.core.contracts import ExperimentProject, GeneralConfig, WorkflowWorker
from physics_lab.core.simulated_devices import SimulatedPendulumDevice
from physics_lab.core.simulator import run_pendulum


class RecordingWorker:
    def __init__(self) -> None:
        self.results: list[dict] = []
        self.errors: list[str] = []
        self.updates: list[tuple[int, str]] = []

    class _Signal:
        def __init__(self, target):
            self.target = target

        def emit(self, *args):
            self.target(*args)

    def __post_init__(self):
        self.progress = self._Signal(lambda *args: self.updates.append(args))
        self.completed = self._Signal(lambda result: self.results.append(result))
        self.failed = self._Signal(lambda message: self.errors.append(message))
        self.cancelled_count = 0
        self.cancelled = self._Signal(lambda: setattr(self, "cancelled_count", self.cancelled_count + 1))


def test_pendulum_uses_device_interface() -> None:
    worker = RecordingWorker()
    worker.__post_init__()
    project = ExperimentProject("test", "pendulum", "1.0.0", GeneralConfig("单摆", "T-001", "2026-08-14"))
    project.plugin_config["length"] = 1.0

    run_pendulum(project, worker, SimulatedPendulumDevice())

    assert not worker.errors
    assert worker.results[0]["points"] == 101
    assert len(worker.updates) == 101


def test_pendulum_can_be_cancelled_during_sampling() -> None:
    worker = RecordingWorker()
    worker.__post_init__()
    project = ExperimentProject("cancelled", "pendulum", "1.0.0", GeneralConfig("单摆", "T-002", "2026-08-14"))
    checks = 0

    def is_cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 5

    run_pendulum(project, worker, SimulatedPendulumDevice(), is_cancelled=is_cancelled)

    assert worker.cancelled_count == 1
    assert not worker.results


def test_pendulum_can_pause_and_resume_sampling() -> None:
    worker = RecordingWorker()
    worker.__post_init__()
    project = ExperimentProject("paused", "pendulum", "1.0.0", GeneralConfig("单摆", "T-003", "2026-08-14"))
    paused = True

    def is_paused() -> bool:
        return paused

    def resume() -> None:
        nonlocal paused
        paused = False

    run_pendulum(
        project,
        worker,
        SimulatedPendulumDevice(),
        is_paused=is_paused,
        wait_until_resumed=resume,
    )

    assert not worker.errors
    assert worker.results[0]["points"] == 101
