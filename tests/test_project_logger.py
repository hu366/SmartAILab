import json

from physics_lab.core.contracts import GeneralConfig
from physics_lab.core.project_logger import ProjectLogger
from physics_lab.core.project_repository import ProjectRepository


def test_project_logger_writes_experiment_and_error_logs(tmp_path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    project = repository.create("pendulum", "1.0.0", GeneralConfig("单摆", "LOG-001", "2026-08-14"))
    logger = ProjectLogger(repository, project)

    logger.info("experiment_started", "开始实验", device_id="simulated-pendulum-01")
    try:
        raise RuntimeError("device disconnected")
    except RuntimeError as exc:
        logger.error("device_error", "设备断开", exc)

    experiment_lines = (tmp_path / "projects" / "LOG-001" / "logs" / "experiment.log").read_text(encoding="utf-8").splitlines()
    error_lines = (tmp_path / "projects" / "LOG-001" / "logs" / "errors.log").read_text(encoding="utf-8").splitlines()
    assert json.loads(experiment_lines[0])["event"] == "experiment_started"
    assert json.loads(experiment_lines[1])["level"] == "ERROR"
    assert json.loads(error_lines[0])["context"]["exception_type"] == "RuntimeError"
    assert "设备断开" in logger.read_text()
