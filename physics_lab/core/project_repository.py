from __future__ import annotations

import json
import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from physics_lab.core.contracts import ExperimentProject, GeneralConfig


class ProjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, plugin_id: str, plugin_version: str, general: GeneralConfig) -> ExperimentProject:
        project_id = general.number.strip() or datetime.now().strftime("%Y%m%d-%H%M%S")
        project = ExperimentProject(project_id, plugin_id, plugin_version, general)
        self.save(project)
        return project

    def save(self, project: ExperimentProject) -> None:
        project.updated_at = datetime.now().isoformat(timespec="seconds")
        project_dir = self.root / project.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        for folder in ("raw", "processed", "results", "logs"):
            (project_dir / folder).mkdir(exist_ok=True)
        target = project_dir / "manifest.json"
        temporary = project_dir / "manifest.json.tmp"
        temporary.write_text(json.dumps(asdict(project), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def write_raw_samples(
        self,
        project: ExperimentProject,
        samples: list[float],
        filename: str = "period_samples.jsonl",
        value_key: str = "period",
    ) -> None:
        rows = [{"index": index, value_key: value} for index, value in enumerate(samples)]
        self.write_raw_rows(project, rows, filename)

    def write_raw_rows(
        self,
        project: ExperimentProject,
        rows: list[dict[str, object]],
        filename: str,
        columns: tuple[str, ...] | None = None,
    ) -> None:
        project_dir = self.root / project.project_id
        raw_dir = project_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / filename
        temporary = raw_dir / f"{filename}.tmp"
        resolved_columns = columns or tuple(rows[0].keys()) if rows else tuple()
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False))
                handle.write("\n")
        temporary.replace(target)
        project.raw_artifacts = [
            item for item in project.raw_artifacts if item.get("path") != f"raw/{filename}"
        ]
        project.raw_artifacts.append(
            {
                "path": f"raw/{filename}",
                "format": "jsonl",
                "samples": len(rows),
                "columns": list(resolved_columns),
            }
        )
        self.save(project)

    def read_raw_rows(self, project: ExperimentProject, filename: str) -> list[dict[str, object]]:
        path = self._project_path(project, filename)
        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("Raw data rows must be JSON objects")
                    rows.append(row)
        return rows

    def read_raw_samples(self, project: ExperimentProject, filename: str, value_key: str) -> list[float]:
        return [float(row[value_key]) for row in self.read_raw_rows(project, filename)]

    def export_raw_csv(
        self,
        project: ExperimentProject,
        filename: str,
        destination: Path,
        columns: tuple[str, ...] | None = None,
    ) -> None:
        rows = self.read_raw_rows(project, filename)
        resolved_columns = columns or tuple(rows[0].keys()) if rows else tuple()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="") as destination_handle:
            writer = csv.writer(destination_handle)
            writer.writerow(resolved_columns)
            for row in rows:
                writer.writerow([row.get(column, "") for column in resolved_columns])

    def _project_path(self, project: ExperimentProject, relative_path: str) -> Path:
        project_dir = (self.root / project.project_id).resolve()
        path = (project_dir / relative_path).resolve()
        if project_dir not in path.parents:
            raise ValueError("Project artifact path escapes the project directory")
        return path

    def list_projects(self) -> list[ExperimentProject]:
        projects: list[ExperimentProject] = []
        for manifest in sorted(self.root.glob("*/manifest.json"), reverse=True):
            try:
                projects.append(self.load(manifest.parent.name))
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return projects

    def load(self, project_id: str) -> ExperimentProject:
        data = json.loads((self.root / project_id / "manifest.json").read_text(encoding="utf-8"))
        general = GeneralConfig(**data.pop("general"))
        return ExperimentProject(general=general, **data)
