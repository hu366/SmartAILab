from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QMargins, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from physics_lab.core.contracts import ExperimentProject


class FaradayAnomalyDialog(QDialog):
    def __init__(self, anomalies: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("异常样本记录")
        self.setMinimumSize(860, 420)
        self.resize(1100, 560)
        table = QTableWidget(len(anomalies), 10)
        table.setHorizontalHeaderLabels([
            "波长(nm)", "点序号", "电流(A)", "磁场(T)", "事件序号",
            "左路", "右路", "R", "异常原因", "模式",
        ])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for row, item in enumerate(anomalies):
            values = (
                item.get("wavelength_nm", "--"),
                item.get("point_index", "--"),
                item.get("current_a", "--"),
                item.get("magnetic_field_t", "--"),
                item.get("event_index", "--"),
                item.get("raw_left", "--"),
                item.get("raw_right", "--"),
                item.get("r", "--"),
                item.get("abnormal_reason", "未知异常"),
                "调试" if item.get("debug") else "正式",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("异常值已从计算中排除，以下记录保留了波长、磁场点、原始通道和异常原因。"))
        layout.addWidget(table, 1)
        layout.addWidget(close)


class FaradayResultPage(QWidget):
    page_id = "result"
    title = "实验分析"
    EXPORT_CHART_SIZE = QSize(1400, 900)

    def __init__(self, project: ExperimentProject, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.repository = repository
        self.wavelength_chart = QChartView()
        self.verdet_chart = QChartView()
        for view in (self.wavelength_chart, self.verdet_chart):
            view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.wavelength_table = QTableWidget(0, 5)
        self.wavelength_table.setHorizontalHeaderLabels(["波长（nm）", "R0", "K（rad/T）", "R²", "V（rad/T/m）"])
        self.wavelength_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.wavelength_table.horizontalHeader().setStretchLastSection(True)
        self.selected_wavelength = None
        self.wavelength_table.cellClicked.connect(self._select_wavelength)

        self.anomaly_button = QPushButton("查看异常记录")
        self.anomaly_button.clicked.connect(self.show_anomalies)
        export = QPushButton("导出数据和图像")
        export.clicked.connect(self.export_all)
        summary_actions = QHBoxLayout()
        summary_actions.addWidget(self.summary, 1)
        summary_actions.addWidget(self.anomaly_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("结果摘要"))
        layout.addLayout(summary_actions)
        layout.addWidget(self.wavelength_table)
        charts = QHBoxLayout()
        charts.addWidget(self.wavelength_chart)
        charts.addWidget(self.verdet_chart)
        layout.addLayout(charts, 1)
        layout.addWidget(export)
        self.refresh()

    def refresh(self) -> None:
        result = self.project.result or {}
        wavelengths = result.get("wavelengths", [])
        self.wavelength_table.setRowCount(len(wavelengths))
        for row, item in enumerate(wavelengths):
            values = (
                item.get("value_nm", "--"),
                item.get("r0", "--"),
                item.get("k_rad_per_t", "--"),
                item.get("r_squared", "--"),
                item.get("v_rad_per_t_m", "--"),
            )
            for column, value in enumerate(values):
                self.wavelength_table.setItem(row, column, QTableWidgetItem(str(value)))
        complete = sum(1 for item in wavelengths if item.get("status") == "complete")
        anomalies = result.get("anomalies", [])
        self.summary.setText(
            f"样品：{result.get('sample', {}).get('name', '--')} · "
            f"已完成波长：{complete}/{len(wavelengths)} · 异常样本：{len(anomalies)}（不参与计算）"
        )
        self.anomaly_button.setText(f"查看异常记录（{len(anomalies)}）")
        self.anomaly_button.setEnabled(bool(anomalies))
        self._render_verdet_chart(wavelengths)
        if wavelengths:
            self._render_wavelength_chart(wavelengths[0])
        else:
            self.wavelength_chart.setChart(QChart())

    def show_anomalies(self) -> None:
        anomalies = list((self.project.result or {}).get("anomalies", []))
        if anomalies:
            FaradayAnomalyDialog(anomalies, self).exec()

    def _select_wavelength(self, row: int, _column: int) -> None:
        wavelengths = self.project.result.get("wavelengths", [])
        if 0 <= row < len(wavelengths):
            self._render_wavelength_chart(wavelengths[row])

    @staticmethod
    def _chart_view(chart: QChart) -> QChartView:
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return view

    @staticmethod
    def _style_data_points(dots: QScatterSeries) -> None:
        dots.setColor(QColor("#000000"))
        dots.setBorderColor(QColor("#000000"))
        dots.setMarkerSize(10.0)

    @staticmethod
    def _prepare_chart(chart: QChart) -> None:
        chart.setMargins(QMargins(80, 50, 80, 80))
        chart.setBackgroundBrush(QColor("#ffffff"))
        chart.createDefaultAxes()
        for axis in chart.axes():
            if not isinstance(axis, QValueAxis):
                continue
            minimum = axis.min()
            maximum = axis.max()
            span = maximum - minimum
            padding = max(abs(minimum), abs(maximum), 1.0) * 0.08 if span <= 0 else span * 0.08
            axis.setRange(minimum - padding, maximum + padding)

    @classmethod
    def _grab_chart(cls, view: QChartView) -> QPixmap:
        original_size = view.size()
        view.resize(cls.EXPORT_CHART_SIZE)
        view.chart().layout().activate()
        view.repaint()
        image = view.grab()
        if original_size.isValid() and not original_size.isEmpty():
            view.resize(original_size)
        return image

    @staticmethod
    def _filename_part(value: object, fallback: str) -> str:
        text = str(value).strip()
        invalid = '<>:"/\\|?*'
        safe = "".join("_" if char in invalid else char for char in text).strip(" .")
        return safe or fallback

    def _export_prefix(self) -> str:
        number = self._filename_part(self.project.general.number, self.project.project_id)
        return f"实验编号{number}_法拉第实验"

    def _render_wavelength_chart(self, wavelength: dict[str, Any]) -> None:
        chart = QChart()
        points = wavelength.get("points", [])
        series = QLineSeries()
        dots = QScatterSeries()
        series.setName(f"{wavelength.get('value_nm', '--')} nm 拟合")
        dots.setName("实验点")
        self._style_data_points(dots)
        for point in sorted(points, key=lambda item: float(item["magnetic_field_t"])):
            b = float(point["magnetic_field_t"])
            theta = float(point.get("theta_rad", 0.0))
            dots.append(b, theta)
            series.append(b, float(wavelength.get("k_rad_per_t", 0.0)) * b + float(wavelength.get("intercept_rad", 0.0)))
        chart.addSeries(series)
        chart.addSeries(dots)
        chart.setTitle(f"{wavelength.get('value_nm', '--')} nm：θ-B（K={wavelength.get('k_rad_per_t', '--')}，R²={wavelength.get('r_squared', '--')}）")
        self._prepare_chart(chart)
        self.wavelength_chart.setChart(chart)

    def _render_verdet_chart(self, wavelengths: list[dict[str, Any]]) -> None:
        chart = QChart()
        series = QLineSeries()
        dots = QScatterSeries()
        series.setName("V-波长")
        dots.setName("实验点")
        self._style_data_points(dots)
        for item in wavelengths:
            if "v_rad_per_t_m" not in item:
                continue
            x = float(item["value_nm"])
            y = float(item["v_rad_per_t_m"])
            series.append(x, y)
            dots.append(x, y)
        chart.addSeries(series)
        chart.addSeries(dots)
        chart.setTitle("V-波长")
        self._prepare_chart(chart)
        self.verdet_chart.setChart(chart)

    def _write_wave_csv(self, destination: Path, wavelength: dict[str, Any]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["序号", "电流(A)", "磁场(T)", "R", "旋光角(rad)", "状态"])
            for point in wavelength.get("points", []):
                writer.writerow([
                    point.get("index", ""), point.get("current_a", ""), point.get("magnetic_field_t", ""),
                    point.get("r", ""), point.get("theta_rad", ""), point.get("status", ""),
                ])

    def _write_result_csv(self, destination: Path, wavelengths: list[dict[str, Any]]) -> None:
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["波长(nm)", "R0", "K(rad/T)", "R²", "V(rad/T/m)"])
            for item in wavelengths:
                writer.writerow([
                    item.get("value_nm", ""), item.get("r0", ""), item.get("k_rad_per_t", ""),
                    item.get("r_squared", ""), item.get("v_rad_per_t_m", ""),
                ])

    def _write_anomaly_csv(self, destination: Path, anomalies: list[dict[str, Any]]) -> None:
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "波长(nm)", "点序号", "电流(A)", "磁场(T)", "事件序号", "采样序号",
                "左路raw", "右路raw", "R", "异常原因", "模式",
            ])
            for item in anomalies:
                writer.writerow([
                    item.get("wavelength_nm", ""), item.get("point_index", ""),
                    item.get("current_a", ""), item.get("magnetic_field_t", ""),
                    item.get("event_index", ""), item.get("sample_index", ""),
                    item.get("raw_left", ""), item.get("raw_right", ""), item.get("r", ""),
                    item.get("abnormal_reason", ""), "debug" if item.get("debug") else "formal",
                ])

    @staticmethod
    def _save_chart(view: QChartView, destination: Path) -> None:
        image = FaradayResultPage._grab_chart(view)
        image.save(str(destination), "PNG")

    def export_all(self) -> None:
        destination = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not destination:
            return
        root = Path(destination)
        prefix = self._export_prefix()
        wavelengths = self.project.result.get("wavelengths", [])
        anomalies = self.project.result.get("anomalies", [])
        try:
            for item in wavelengths:
                value = str(item.get("value_nm", "wavelength")).replace(".", "_")
                self._write_wave_csv(root / f"{prefix}_波长{value}nm_数据.csv", item)
                chart = QChart()
                points = item.get("points", [])
                dots = QScatterSeries()
                line = QLineSeries()
                self._style_data_points(dots)
                for point in points:
                    b = float(point["magnetic_field_t"])
                    theta = float(point.get("theta_rad", 0.0))
                    dots.append(b, theta)
                    line.append(b, float(item.get("k_rad_per_t", 0.0)) * b + float(item.get("intercept_rad", 0.0)))
                chart.addSeries(line)
                chart.addSeries(dots)
                self._prepare_chart(chart)
                self._save_chart(self._chart_view(chart), root / f"{prefix}_波长{value}nm_旋光角磁场图.png")
            self._write_result_csv(root / f"{prefix}_结果汇总.csv", wavelengths)
            self._write_anomaly_csv(root / f"{prefix}_异常记录.csv", anomalies)
            self._save_chart(self.verdet_chart, root / f"{prefix}_维尔德常数波长图.png")
            self._save_chart(self.wavelength_chart, root / f"{prefix}_旋光角磁场图_当前波长.png")
            self._save_composite_chart(root / f"{prefix}_全部图表.png", wavelengths)
            QMessageBox.information(self, "导出完成", f"文件已导出到：{root}")
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _save_composite_chart(self, destination: Path, wavelengths: list[dict[str, Any]]) -> None:
        charts: list[QPixmap] = []
        for item in wavelengths:
            chart = QChart()
            dots = QScatterSeries()
            line = QLineSeries()
            self._style_data_points(dots)
            for point in sorted(item.get("points", []), key=lambda row: float(row["magnetic_field_t"])):
                b = float(point["magnetic_field_t"])
                theta = float(point.get("theta_rad", 0.0))
                dots.append(b, theta)
                line.append(b, float(item.get("k_rad_per_t", 0.0)) * b + float(item.get("intercept_rad", 0.0)))
            chart.addSeries(line)
            chart.addSeries(dots)
            chart.setTitle(f"{item.get('value_nm', '--')} nm θ-B")
            self._prepare_chart(chart)
            view = QChartView(chart)
            view.setRenderHint(QPainter.RenderHint.Antialiasing)
            charts.append(self._grab_chart(view))
        verdet = self._grab_chart(self.verdet_chart)
        columns = 2
        tile_width = self.EXPORT_CHART_SIZE.width()
        tile_height = self.EXPORT_CHART_SIZE.height()
        rows = max(1, (len(charts) + 1 + columns - 1) // columns)
        canvas = QPixmap(columns * tile_width, rows * tile_height)
        canvas.fill("white")
        painter = QPainter(canvas)
        for index, image in enumerate(charts + [verdet]):
            painter.drawPixmap((index % columns) * tile_width, (index // columns) * tile_height, image)
        painter.end()
        canvas.save(str(destination), "PNG")
