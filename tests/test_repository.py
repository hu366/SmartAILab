from pathlib import Path

from physics_lab.core.contracts import GeneralConfig
from physics_lab.core.project_repository import ProjectRepository


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
