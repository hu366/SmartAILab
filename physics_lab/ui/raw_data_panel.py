from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from physics_lab.core.contracts import ExperimentProject
from physics_lab.core.project_repository import ProjectRepository


class RawDataPanel(QGroupBox):
    def __init__(
        self,
        project: ExperimentProject,
        repository: ProjectRepository,
        filename: str,
        columns: tuple[tuple[str, str], ...],
        recalculate: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__("原始数据", parent)
        self.project = project
        self.repository = repository
        self.filename = filename
        self.columns = columns
        self.recalculate_callback = recalculate
        self.status = QLabel()
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([label for _key, label in columns])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(240)

        export_button = QPushButton("导出 CSV")
        recalculate_button = QPushButton("重新计算")
        export_button.clicked.connect(self.export_csv)
        recalculate_button.clicked.connect(self.recalculate)
        actions = QHBoxLayout()
        actions.addWidget(export_button)
        actions.addWidget(recalculate_button)
        actions.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        try:
            rows = self.repository.read_raw_rows(self.project, self.filename)
        except (OSError, KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            self.status.setText(f"原始数据不可用：{exc}")
            self.table.setRowCount(0)
            return
        visible = rows[:200]
        self.table.setRowCount(len(visible))
        for row_index, row in enumerate(visible):
            for column_index, (key, _label) in enumerate(self.columns):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(row.get(key, ""))))
        suffix = "（仅显示前 200 条）" if len(rows) > len(visible) else ""
        self.status.setText(f"共 {len(rows)} 条数据{suffix}")

    def export_csv(self) -> None:
        default_path = str(Path(self.project.project_id).with_suffix(".csv"))
        destination, _ = QFileDialog.getSaveFileName(self, "导出原始数据", default_path, "CSV 文件 (*.csv)")
        if not destination:
            return
        try:
            self.repository.export_raw_csv(
                self.project,
                self.filename,
                Path(destination),
                tuple(key for key, _label in self.columns),
            )
            self.status.setText(f"已导出：{destination}")
        except (OSError, KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def recalculate(self) -> None:
        try:
            self.recalculate_callback()
            self.refresh()
        except (OSError, KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            QMessageBox.critical(self, "重新计算失败", str(exc))
