from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from physics_lab.core.contracts import ExperimentProject
from physics_lab.core.project_repository import ProjectRepository


class ConfigTableDialog(QDialog):
    """Large editor dialog for one repeatable experiment configuration table."""

    def __init__(
        self,
        title: str,
        headers: list[str],
        rows: list[list[float]],
        unit_options: list[str] | None = None,
        unit: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 380)
        self.resize(720, 520)
        self._headers = headers
        self._unit_last = unit
        self._unit = unit
        self._result: list[list[float]] | None = None

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        for row in rows:
            self._append_row(row)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("在表格中编辑数值，使用下方按钮调整测量顺序。"))
        if unit_options:
            unit_row = QHBoxLayout()
            unit_row.addWidget(QLabel("单位"))
            self.unit = QComboBox()
            self.unit.addItems(unit_options)
            self.unit.setCurrentText(unit)
            self.unit.currentTextChanged.connect(self._convert_unit)
            unit_row.addWidget(self.unit)
            unit_row.addStretch()
            layout.addLayout(unit_row)
        else:
            self.unit = None
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        add = QPushButton("添加")
        remove = QPushButton("删除")
        up = QPushButton("上移")
        down = QPushButton("下移")
        add.clicked.connect(self._add_default_row)
        remove.clicked.connect(self._remove_row)
        up.clicked.connect(lambda: self._move_row(-1))
        down.clicked.connect(lambda: self._move_row(1))
        for button in (add, remove, up, down):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_values)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        layout.addWidget(buttons)

    def _append_row(self, values: list[float]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(f"{value:g}"))

    def _add_default_row(self) -> None:
        self._append_row([500.0] if len(self._headers) == 1 else [0.0, 0.0])
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)

    def _remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _move_row(self, offset: int) -> None:
        row = self.table.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.table.rowCount():
            return
        values = [self.table.item(row, column).text() for column in range(self.table.columnCount())]
        target_values = [self.table.item(target, column).text() for column in range(self.table.columnCount())]
        for column, value in enumerate(target_values):
            self.table.setItem(row, column, QTableWidgetItem(value))
        for column, value in enumerate(values):
            self.table.setItem(target, column, QTableWidgetItem(value))
        self.table.setCurrentCell(target, 0)

    def _convert_unit(self, new_unit: str) -> None:
        old_unit = self._unit_last
        if old_unit == new_unit:
            return
        if len(self._headers) == 1:
            old_scale = 1.0 if old_unit == "nm" else 1000.0
            new_scale = 1.0 if new_unit == "nm" else 1000.0
        else:
            old_scale = 0.001 if old_unit == "mT" else 1.0
            new_scale = 0.001 if new_unit == "mT" else 1.0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0 if len(self._headers) == 1 else 1)
            if item is None:
                continue
            try:
                value = float(item.text())
            except ValueError:
                continue
            item.setText(f"{value * old_scale / new_scale:g}")
        self._unit_last = new_unit
        self._unit = new_unit

    def _accept_values(self) -> None:
        values: list[list[float]] = []
        try:
            for row in range(self.table.rowCount()):
                row_values = []
                for column, header in enumerate(self._headers):
                    item = self.table.item(row, column)
                    if item is None:
                        raise ValueError(f"第 {row + 1} 行的{header}不能为空")
                    row_values.append(float(item.text().strip()))
                values.append(row_values)
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "配置无效", str(exc))
            return
        self._result = values
        self.accept()

    def values(self) -> list[list[float]]:
        return self._result or []

    def selected_unit(self) -> str:
        return self._unit


class FaradayConfigPage(QWidget):
    page_id = "plugin-config"
    title = "实验参数"

    def __init__(
        self,
        project: ExperimentProject,
        parent: QWidget | None = None,
        repository: ProjectRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.repository = repository
        config = project.plugin_config
        sample = config.get("sample", {})
        units = config.get("units", {})
        serial = config.get("serial", {})

        self.sample_name = QLineEdit(str(sample.get("name", "")))
        self.sample_material = QLineEdit(str(sample.get("material", "")))
        self.experiment_name = QLineEdit(project.general.name)
        self.experiment_number = QLineEdit(project.general.number)
        self.length = QLineEdit(f"{self._display_length(float(sample.get('length_m', 0.01)), str(units.get('length', 'mm'))):g}")
        self.length.setValidator(QDoubleValidator(0.001, 10000.0, 4, self.length))
        self.length.setPlaceholderText("请输入长度")
        self.length_unit = QComboBox()
        self.length_unit.addItems(["mm", "m"])
        self.length_unit.setCurrentText(str(units.get("length", "mm")))

        wavelength_unit = str(units.get("wavelength", "nm"))
        magnetic_unit = str(units.get("magnetic_field", "mT"))
        self.wavelength_unit = wavelength_unit
        self.magnetic_unit = magnetic_unit
        self.wavelength_rows = [
            [float(row.get("value_nm", 500.0)) / (1000.0 if wavelength_unit == "um" else 1.0)]
            for row in config.get("wavelengths", [])
        ] or [[500.0]]
        self.field_rows = [
            [float(row.get("current_a", 0.0)), float(row.get("magnetic_field_t", 0.0)) / (0.001 if magnetic_unit == "mT" else 1.0)]
            for row in config.get("field_points", [])
        ] or [[0.0, 0.0], [1.0, 1.0]]

        self.wavelength_summary = QLabel()
        self.field_summary = QLabel()
        self.wavelength_summary.setObjectName("muted")
        self.field_summary.setObjectName("muted")
        wavelength_button = QPushButton("打开波长配置")
        field_button = QPushButton("打开磁场点配置")
        wavelength_button.clicked.connect(self._edit_wavelengths)
        field_button.clicked.connect(self._edit_field_points)
        self._refresh_summaries()

        self.port = QLineEdit(str(serial.get("port", "")))
        self.port.setPlaceholderText("例如 COM8")
        self.baudrate = QLineEdit(str(serial.get("baudrate", 115200)))
        self.baudrate.setValidator(QIntValidator(1200, 2000000, self.baudrate))
        self.baudrate.setPlaceholderText("1200 - 2000000")
        self.samples_per_point = QLineEdit(str(serial.get("samples_per_point", 10)))
        self.samples_per_point.setValidator(QIntValidator(1, 10000, self.samples_per_point))
        self.samples_per_point.setPlaceholderText("1 - 10000")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("实验信息"))
        general_box = QGroupBox()
        general_form = QFormLayout(general_box)
        general_form.addRow("实验名称", self.experiment_name)
        general_form.addRow("实验编号", self.experiment_number)
        layout.addWidget(general_box)

        layout.addWidget(QLabel("样品信息"))
        sample_box = QGroupBox()
        sample_form = QFormLayout(sample_box)
        sample_form.addRow("样品名称", self.sample_name)
        sample_form.addRow("材料/说明", self.sample_material)
        length_row = QHBoxLayout()
        length_row.addWidget(self.length)
        length_row.addWidget(self.length_unit)
        sample_form.addRow("样品长度", length_row)
        layout.addWidget(sample_box)

        layout.addWidget(QLabel("实验测量配置"))
        config_box = QGroupBox()
        config_form = QFormLayout(config_box)
        wavelength_row = QHBoxLayout()
        wavelength_row.addWidget(wavelength_button)
        wavelength_row.addWidget(self.wavelength_summary, 1)
        config_form.addRow("波长", wavelength_row)
        field_row = QHBoxLayout()
        field_row.addWidget(field_button)
        field_row.addWidget(self.field_summary, 1)
        config_form.addRow("磁场点", field_row)
        layout.addWidget(config_box)

        layout.addWidget(QLabel("串口采集"))
        serial_box = QGroupBox()
        serial_form = QFormLayout(serial_box)
        serial_form.addRow("串口端口", self.port)
        serial_form.addRow("波特率", self.baudrate)
        serial_form.addRow("每点采集数", self.samples_per_point)
        layout.addWidget(serial_box)

        layout.addWidget(QLabel("配置模板"))
        template_row = QHBoxLayout()
        save_template = QPushButton("保存为默认模板")
        load_template = QPushButton("加载默认模板")
        save_template.clicked.connect(self._save_template)
        load_template.clicked.connect(self._load_template)
        template_row.addWidget(save_template)
        template_row.addWidget(load_template)
        template_row.addStretch()
        layout.addLayout(template_row)
        layout.addStretch()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

    @staticmethod
    def _display_length(value_m: float, unit: str) -> float:
        return value_m * 1000 if unit == "mm" else value_m

    def _refresh_summaries(self) -> None:
        values = ", ".join(f"{row[0]:g}" for row in self.wavelength_rows[:6])
        if len(self.wavelength_rows) > 6:
            values += ", ..."
        self.wavelength_summary.setText(f"{len(self.wavelength_rows)} 项：{values} {self.wavelength_unit}")
        point_text = ", ".join(f"I={row[0]:g} A / B={row[1]:g} {self.magnetic_unit}" for row in self.field_rows[:4])
        if len(self.field_rows) > 4:
            point_text += ", ..."
        self.field_summary.setText(f"{len(self.field_rows)} 点：{point_text}")

    def _edit_wavelengths(self) -> None:
        dialog = ConfigTableDialog(
            "波长配置",
            [f"波长（{self.wavelength_unit}）"],
            self.wavelength_rows,
            ["nm", "um"],
            self.wavelength_unit,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.wavelength_rows = dialog.values()
            self.wavelength_unit = dialog.selected_unit()
            self._refresh_summaries()

    def _edit_field_points(self) -> None:
        dialog = ConfigTableDialog(
            "磁场点配置",
            ["电流（A）", f"磁场（{self.magnetic_unit}）"],
            self.field_rows,
            ["mT", "T"],
            self.magnetic_unit,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.field_rows = dialog.values()
            self.magnetic_unit = dialog.selected_unit()
            self._refresh_summaries()

    def _template_payload(self) -> dict[str, object]:
        return {
            "version": 1,
            "units": {
                "wavelength": self.wavelength_unit,
                "magnetic_field": self.magnetic_unit,
            },
            "wavelength_rows": [list(row) for row in self.wavelength_rows],
            "field_rows": [list(row) for row in self.field_rows],
        }

    def _save_template(self) -> None:
        if self.repository is None:
            QMessageBox.warning(self, "模板不可用", "当前页面没有连接项目存储。")
            return
        try:
            self.repository.save_plugin_template("faraday", self._template_payload())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "模板已保存", "波长配置和磁场点配置已保存为默认模板。")

    def _load_template(self) -> None:
        if self.repository is None:
            QMessageBox.warning(self, "模板不可用", "当前页面没有连接项目存储。")
            return
        try:
            template = self.repository.load_plugin_template("faraday")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "加载失败", str(exc))
            return
        if template is None:
            QMessageBox.information(self, "没有默认模板", "请先保存一个默认模板。")
            return
        try:
            units = template.get("units", {})
            wavelength_rows = template["wavelength_rows"]
            field_rows = template["field_rows"]
            self.wavelength_unit = str(units.get("wavelength", "nm"))
            self.magnetic_unit = str(units.get("magnetic_field", "mT"))
            self.wavelength_rows = [[float(row[0])] for row in wavelength_rows]
            self.field_rows = [[float(row[0]), float(row[1])] for row in field_rows]
            if not self.wavelength_rows or not self.field_rows:
                raise ValueError("模板中没有有效的波长或磁场点")
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            QMessageBox.critical(self, "模板无效", str(exc))
            return
        self._refresh_summaries()
        QMessageBox.information(self, "模板已加载", "默认波长和磁场点配置已加载。")

    def validate(self) -> tuple[bool, str]:
        if not self.experiment_name.text().strip():
            return False, "请输入实验名称。"
        if not self.experiment_number.text().strip():
            return False, "请输入实验编号。"
        if (
            self.repository is not None
            and self.repository.experiment_number_exists(
                self.experiment_number.text(),
                exclude_project_id=self.project.project_id,
            )
        ):
            return False, f"实验编号“{self.experiment_number.text().strip()}”已存在，请使用其他编号。"
        if not self.sample_name.text().strip():
            return False, "请输入样品名称。"
        if not self.sample_material.text().strip():
            return False, "请输入材料或样品说明。"
        try:
            length_value = float(self.length.text().strip())
        except ValueError:
            return False, "样品长度必须是有效数字。"
        if not 0.001 <= length_value <= 10000.0:
            return False, "样品长度必须在 0.001 到 10000 之间。"
        try:
            baudrate = int(self.baudrate.text().strip())
        except ValueError:
            return False, "波特率必须是整数。"
        if not 1200 <= baudrate <= 2000000:
            return False, "波特率必须在 1200 到 2000000 之间。"
        try:
            samples_per_point = int(self.samples_per_point.text().strip())
        except ValueError:
            return False, "每点采集数必须是整数。"
        if not 1 <= samples_per_point <= 10000:
            return False, "每点采集数必须在 1 到 10000 之间。"
        if not self.wavelength_rows:
            return False, "至少配置一个波长。"
        if any(row[0] <= 0 for row in self.wavelength_rows):
            return False, "波长必须大于 0。"
        if len(self.field_rows) < 2:
            return False, "至少配置零场点和一个磁场点。"
        if sum(1 for row in self.field_rows if row[1] == 0) != 1:
            return False, "必须配置且只能配置一个 B=0 的零场点。"
        if not self.port.text().strip():
            return False, "请输入串口端口，法拉第实验不使用模拟设备。"
        return True, ""

    def save_to_project(self, project: ExperimentProject) -> None:
        project.general.name = self.experiment_name.text().strip()
        project.general.number = self.experiment_number.text().strip()
        length_unit = self.length_unit.currentText()
        length_value = float(self.length.text().strip())
        length_m = length_value / 1000.0 if length_unit == "mm" else length_value
        wavelength_scale = 1000.0 if self.wavelength_unit == "um" else 1.0
        magnetic_scale = 0.001 if self.magnetic_unit == "mT" else 1.0
        project.plugin_config = {
            "sample": {
                "name": self.sample_name.text().strip(),
                "material": self.sample_material.text().strip(),
                "length_m": length_m,
            },
            "units": {
                "wavelength": self.wavelength_unit,
                "magnetic_field": self.magnetic_unit,
                "length": length_unit,
                "angle": "rad",
            },
            "wavelengths": [
                {"id": f"wavelength-{index}", "value_nm": row[0] * wavelength_scale}
                for index, row in enumerate(self.wavelength_rows, start=1)
            ],
            "field_points": [
                {
                    "id": f"point-{index}",
                    "current_a": row[0],
                    "magnetic_field_t": row[1] * magnetic_scale,
                }
                for index, row in enumerate(self.field_rows, start=1)
            ],
            "serial": {
                "port": self.port.text().strip(),
                "baudrate": int(self.baudrate.text().strip()),
                "samples_per_point": int(self.samples_per_point.text().strip()),
            },
        }
