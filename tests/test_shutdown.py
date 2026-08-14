from types import SimpleNamespace

from physics_lab.ui.main_window import WorkflowPage


class FakeWorker:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeThread:
    def __init__(self, finished: bool = True) -> None:
        self.finished = finished
        self.quit_called = False
        self.wait_timeout = None

    def quit(self) -> None:
        self.quit_called = True

    def wait(self, timeout: int) -> bool:
        self.wait_timeout = timeout
        return self.finished


class FakeRepository:
    def __init__(self) -> None:
        self.saved = []

    def save(self, project) -> None:
        self.saved.append(project.status)


class FakeLogger:
    def __init__(self) -> None:
        self.events = []

    def warning(self, event: str, message: str) -> None:
        self.events.append((event, message))


def make_workflow(thread: FakeThread) -> WorkflowPage:
    page = WorkflowPage.__new__(WorkflowPage)
    page.thread = thread
    page.worker = FakeWorker()
    page.run_terminal = False
    page.page_ids = ["plugin-config", "run", "result"]
    page.index = 1
    page.project = SimpleNamespace(status="running", current_step="run")
    page.repository = FakeRepository()
    page.logger = FakeLogger()
    return page


def test_shutdown_cancels_worker_and_persists_cancelled_project() -> None:
    thread = FakeThread()
    page = make_workflow(thread)

    assert page.stop_for_shutdown(timeout_ms=1234)
    assert page.worker.cancelled
    assert thread.quit_called
    assert thread.wait_timeout == 1234
    assert page.project.status == "cancelled"
    assert page.project.current_step == "run"
    assert page.repository.saved == ["cancelled"]
    assert page.logger.events[0][0] == "experiment_cancelled_on_shutdown"


def test_shutdown_reports_when_worker_does_not_stop_in_time() -> None:
    page = make_workflow(FakeThread(finished=False))

    assert not page.stop_for_shutdown()
    assert page.project.status == "running"
    assert not page.repository.saved
