from pathlib import Path

import pytest

from physics_lab.core.contracts import GeneralConfig
from physics_lab.core.project_repository import (
    ProjectAlreadyExistsError,
    ProjectMigrationError,
    ProjectRepository,
)


def test_project_round_trip(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    project = repository.create("pendulum", "1.0.0", GeneralConfig("单摆", "2026-001", "2026-08-14"))
    project.plugin_config["length"] = 1.25
    project.status = "running"
    repository.save(project)
    repository.write_raw_samples(project, [2.0, 2.1])

    restored = repository.load(project.project_id)
    assert restored.general.name == "单摆"
    assert restored.plugin_config["length"] == 1.25
    assert restored.status == "running"
    assert restored.raw_artifacts == [
        {
            "path": "raw/period_samples.jsonl",
            "format": "jsonl",
            "samples": 2,
            "columns": ["index", "period"],
        }
    ]
    raw_path = tmp_path / "projects" / project.project_id / "raw" / "period_samples.jsonl"
    assert raw_path.read_text(encoding="utf-8") == '{"index": 0, "period": 2.0}\n{"index": 1, "period": 2.1}\n'
    assert repository.read_raw_samples(restored, "raw/period_samples.jsonl", "period") == [2.0, 2.1]
    export_path = tmp_path / "exports" / "periods.csv"
    repository.export_raw_csv(restored, "raw/period_samples.jsonl", export_path, ("index", "period"))
    assert export_path.read_text(encoding="utf-8") == "index,period\n0,2.0\n1,2.1\n"
    repository.write_raw_rows(
        restored,
        [{"timestamp": "10:00", "temperature": 21.5, "humidity": 45.0}],
        "environment.jsonl",
        ("timestamp", "temperature", "humidity"),
    )
    environment = repository.read_raw_rows(restored, "raw/environment.jsonl")
    assert environment == [{"timestamp": "10:00", "temperature": 21.5, "humidity": 45.0}]
    environment_csv = tmp_path / "exports" / "environment.csv"
    repository.export_raw_csv(
        restored,
        "raw/environment.jsonl",
        environment_csv,
        ("timestamp", "temperature", "humidity"),
    )
    assert environment_csv.read_text(encoding="utf-8") == "timestamp,temperature,humidity\n10:00,21.5,45.0\n"
    assert [item.project_id for item in repository.list_projects()] == [project.project_id]


def test_duplicate_experiment_number_is_rejected(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    first = repository.create("pendulum", "1.0.0", GeneralConfig("第一次实验", "2026-001", "2026-08-14"))

    assert repository.experiment_number_exists("2026-001")
    assert not repository.experiment_number_exists(" 2026-001 ", exclude_project_id=first.project_id)

    with pytest.raises(ProjectAlreadyExistsError):
        repository.create(
            "temperature",
            "1.0.0",
            GeneralConfig("第二次实验", "2026-001", "2026-08-14"),
        )

    projects = repository.list_projects()
    assert len(projects) == 1
    assert projects[0].general.name == "第一次实验"


def test_experiment_number_exists_detects_number_changed_to_another_project(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    first = repository.create("faraday", "1.0.0", GeneralConfig("第一次实验", "2026-001", "2026-08-14"))
    second = repository.create("faraday", "1.0.0", GeneralConfig("第二次实验", "2026-002", "2026-08-14"))

    second.general.number = "2026-001"

    assert repository.experiment_number_exists(second.general.number, exclude_project_id=second.project_id)
    assert not repository.experiment_number_exists(first.general.number, exclude_project_id=first.project_id)


def test_project_number_cannot_escape_repository_root(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")

    with pytest.raises(ValueError, match="directory-safe"):
        repository.create("pendulum", "1.0.0", GeneralConfig("非法编号", "..\\outside", "2026-08-14"))


def test_delete_removes_project_directory(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    project = repository.create("pendulum", "1.0.0", GeneralConfig("待删除", "delete-me", "2026-08-14"))
    repository.delete(project.project_id)

    assert not (tmp_path / "projects" / "delete-me").exists()
    assert repository.list_projects() == []


def test_legacy_manifest_is_migrated_and_saved(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    project_dir = tmp_path / "projects" / "legacy"
    project_dir.mkdir(parents=True)
    (project_dir / "manifest.json").write_text(
        '{"project_id":"legacy","plugin_id":"pendulum","general":{"name":"旧项目"}}',
        encoding="utf-8",
    )

    project = repository.load("legacy")

    assert project.schema_version == 2
    assert project.general.number == "legacy"
    assert project.status == "draft"
    saved = (project_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"schema_version": 2' in saved


def test_newer_manifest_schema_is_rejected(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "projects")
    project_dir = tmp_path / "projects" / "future"
    project_dir.mkdir(parents=True)
    (project_dir / "manifest.json").write_text(
        '{"schema_version":999,"project_id":"future","plugin_id":"pendulum",'
        '"plugin_version":"1.0.0","general":{"name":"未来项目","number":"future",'
        '"experiment_date":"2026-08-14"}}',
        encoding="utf-8",
    )

    with pytest.raises(ProjectMigrationError, match="newer than supported"):
        repository.load("future")
