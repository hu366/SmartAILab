from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


class ProjectLogger:
    """Append-only JSONL logs scoped to one experiment project."""

    def __init__(self, repository, project) -> None:
        self.project_dir = repository.root / project.project_id
        self.logs_dir = self.project_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.experiment_log = self.logs_dir / "experiment.log"
        self.error_log = self.logs_dir / "errors.log"

    def info(self, event: str, message: str, **context: Any) -> None:
        self._write("INFO", event, message, context)

    def warning(self, event: str, message: str, **context: Any) -> None:
        self._write("WARNING", event, message, context)

    def error(self, event: str, message: str, exception: BaseException | None = None, **context: Any) -> None:
        if exception is not None:
            context = {
                **context,
                "exception_type": type(exception).__name__,
                "traceback": "".join(traceback.format_exception(exception)),
            }
        entry = self._entry("ERROR", event, message, context)
        self._append(self.experiment_log, entry)
        self._append(self.error_log, entry)

    def _write(self, level: str, event: str, message: str, context: dict[str, Any]) -> None:
        self._append(self.experiment_log, self._entry(level, event, message, context))

    @staticmethod
    def _entry(level: str, event: str, message: str, context: dict[str, Any]) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "level": level,
                "event": event,
                "message": message,
                "context": context,
            },
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _append(path: Path, entry: str) -> None:
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(entry)
                handle.write("\n")
        except OSError:
            # Logging must not make a hardware experiment fail.
            return

    def read_text(self) -> str:
        sections: list[str] = []
        for title, path in (("实验日志", self.experiment_log), ("错误日志", self.error_log)):
            if path.exists():
                sections.append(f"[{title}]\n{path.read_text(encoding='utf-8')}")
        return "\n".join(sections) or "暂无日志"

