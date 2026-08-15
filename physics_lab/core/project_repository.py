from __future__ import annotations

import json
import csv
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from physics_lab.core.contracts import PROJECT_SCHEMA_VERSION, ExperimentProject, GeneralConfig


class ProjectAlreadyExistsError(FileExistsError):
    """Raised when an experiment number already identifies a project."""


class ProjectMigrationError(ValueError):
    """Raised when a project manifest cannot be migrated safely."""


class ProjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, plugin_id: str, plugin_version: str, general: GeneralConfig) -> ExperimentProject:
        project_id = general.number.strip() or datetime.now().strftime("%Y%m%d-%H%M%S")
        project_dir = self._project_dir(project_id)
        try:
            project_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ProjectAlreadyExistsError(
                f"Project number '{project_id}' already exists"
            ) from exc
        project = ExperimentProject(project_id, plugin_id, plugin_version, general)
        self.save(project)
        return project

    def experiment_number_exists(self, number: str, exclude_project_id: str = "") -> bool:
        """Return whether an experiment number belongs to another saved project."""
        normalized_number = number.strip()
        if not normalized_number:
            return False
        excluded_id = exclude_project_id.strip()
        return any(
            project.project_id != excluded_id
            and project.general.number.strip() == normalized_number
            for project in self.list_projects()
        )

    def save(self, project: ExperimentProject) -> None:
        project.updated_at = datetime.now().isoformat(timespec="seconds")
        project_dir = self._project_dir(project.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        for folder in ("raw", "processed", "results", "logs"):
            (project_dir / folder).mkdir(exist_ok=True)
        target = project_dir / "manifest.json"
        temporary = project_dir / "manifest.json.tmp"
        temporary.write_text(json.dumps(asdict(project), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def delete(self, project_id: str) -> None:
        project_dir = self._project_dir(project_id)
        if not (project_dir / "manifest.json").is_file():
            raise FileNotFoundError(f"Project '{project_id}' does not exist")
        shutil.rmtree(project_dir)

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
        project_dir = self._project_dir(project.project_id)
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

    def delete_raw_file(self, project: ExperimentProject, filename: str) -> None:
        """Delete one plugin-owned raw artifact and update its manifest entry."""
        path = self._project_path(project, f"raw/{filename}")
        if path.exists():
            path.unlink()
        project.raw_artifacts = [
            item for item in project.raw_artifacts if item.get("path") != f"raw/{filename}"
        ]
        self.save(project)

    def save_plugin_template(self, plugin_id: str, template: dict[str, object]) -> None:
        """Persist a reusable plugin configuration outside any experiment project."""
        templates_dir = self.root / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        target = templates_dir / f"{plugin_id}.json"
        temporary = templates_dir / f"{plugin_id}.json.tmp"
        temporary.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def load_plugin_template(self, plugin_id: str) -> dict[str, object] | None:
        """Load a reusable plugin configuration, if one has been saved."""
        path = self.root / "templates" / f"{plugin_id}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Plugin template '{plugin_id}' must be a JSON object")
        return data

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
        project_dir = self._project_dir(project.project_id)
        path = (project_dir / relative_path).resolve()
        if project_dir not in path.parents:
            raise ValueError("Project artifact path escapes the project directory")
        return path

    def _project_dir(self, project_id: str) -> Path:
        root = self.root.resolve()
        project_dir = (root / project_id).resolve()
        if project_dir.parent != root:
            raise ValueError("Project number must be a single directory-safe identifier")
        return project_dir

    def list_projects(self) -> list[ExperimentProject]:
        projects: list[ExperimentProject] = []
        for manifest in sorted(self.root.glob("*/manifest.json"), reverse=True):
            try:
                projects.append(self.load(manifest.parent.name))
            except (OSError, KeyError, TypeError, json.JSONDecodeError, ProjectMigrationError):
                continue
        return projects

    def load(self, project_id: str) -> ExperimentProject:
        data = json.loads((self._project_dir(project_id) / "manifest.json").read_text(encoding="utf-8"))
        data, migrated = self._migrate_manifest(data, project_id)
        general = GeneralConfig(**data.pop("general"))
        project = ExperimentProject(general=general, **data)
        if migrated:
            self.save(project)
        return project

    @staticmethod
    def _migrate_manifest(data: object, project_id: str) -> tuple[dict[str, object], bool]:
        if not isinstance(data, dict):
            raise ProjectMigrationError("Project manifest must be a JSON object")
        migrated = False
        data = dict(data)
        try:
            schema_version = int(data.get("schema_version", 1))
        except (TypeError, ValueError) as exc:
            raise ProjectMigrationError("Project manifest has an invalid schema_version") from exc
        if schema_version > PROJECT_SCHEMA_VERSION:
            raise ProjectMigrationError(
                f"Project schema v{schema_version} is newer than supported v{PROJECT_SCHEMA_VERSION}"
            )

        defaults: dict[str, object] = {
            "project_id": project_id,
            "plugin_version": "0.0.0",
            "status": "draft",
            "current_step": "plugin-config",
            "plugin_config": {},
            "result": {},
            "device_metadata": {},
            "raw_artifacts": [],
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
                migrated = True

        general = data.get("general")
        if not isinstance(general, dict):
            raise ProjectMigrationError("Project manifest is missing a valid general configuration")
        general = dict(general)
        for key, default in {
            "name": project_id,
            "number": project_id,
            "experiment_date": "",
        }.items():
            if key not in general:
                general[key] = default
                migrated = True
        data["general"] = general

        if data.get("project_id") != project_id:
            data["project_id"] = project_id
            migrated = True
        if schema_version != PROJECT_SCHEMA_VERSION:
            migrated = True
        data["schema_version"] = PROJECT_SCHEMA_VERSION
        return data, migrated
