from __future__ import annotations

import math
import time
from typing import Any

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from physics_lab.core.contracts import ExperimentProject
from physics_lab.plugins.faraday.controller import FaradayController


class OscilloscopeChartView(QChartView):
    """Chart view with wheel zoom and left-button X/Y panning."""

    view_changed = Signal()

    def __init__(self, chart: QChart, parent: QWidget | None = None) -> None:
        super().__init__(chart, parent)
        self._dragging = False
        self._last_x = 0.0
        self._last_y = 0.0
        self._manual_view = False
        self._fixed_y_range: tuple[float, float] | None = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _x_axis(self) -> QValueAxis | None:
        axis = self.chart().axisX()
        return axis if isinstance(axis, QValueAxis) else None

    def _y_axis(self) -> QValueAxis | None:
        axis = self.chart().axisY()
        return axis if isinstance(axis, QValueAxis) else None

    def _axis_value_at(self, position) -> tuple[float, float, float, float] | None:
        x_axis = self._x_axis()
        y_axis = self._y_axis()
        plot = self.chart().plotArea()
        if x_axis is None or y_axis is None or plot.width() <= 0 or plot.height() <= 0:
            return None
        x_ratio = min(1.0, max(0.0, (position.x() - plot.left()) / plot.width()))
        y_ratio = min(1.0, max(0.0, (position.y() - plot.top()) / plot.height()))
        x_span = max(x_axis.max() - x_axis.min(), 1e-9)
        y_span = max(y_axis.max() - y_axis.min(), 1e-9)
        return (
            x_axis.min() + x_span * x_ratio,
            y_axis.max() - y_span * y_ratio,
            x_ratio,
            y_ratio,
        )

    def wheelEvent(self, event) -> None:
        axis = self._x_axis()
        if axis is None or event.angleDelta().y() == 0:
            event.ignore()
            return
        plot = self.chart().plotArea()
        if plot.width() <= 0:
            event.ignore()
            return
        ratio = min(1.0, max(0.0, (event.position().x() - plot.left()) / plot.width()))
        span = max(axis.max() - axis.min(), 1e-9)
        center = axis.min() + span * ratio
        factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        new_span = min(max(span * factor, 1e-6), 1_000_000.0)
        axis.setRange(center - new_span * ratio, center + new_span * (1.0 - ratio))
        self._manual_view = True
        self.view_changed.emit()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_x = event.position().x()
            self._last_y = event.position().y()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        x_axis = self._x_axis()
        y_axis = self._y_axis()
        plot = self.chart().plotArea()
        if x_axis is not None and y_axis is not None and plot.width() > 0 and plot.height() > 0:
            delta_x = event.position().x() - self._last_x
            delta_y = event.position().y() - self._last_y
            x_span = x_axis.max() - x_axis.min()
            y_span = y_axis.max() - y_axis.min()
            x_delta_value = -delta_x / plot.width() * x_span
            x_axis.setRange(x_axis.min() + x_delta_value, x_axis.max() + x_delta_value)
            if self._fixed_y_range is None:
                y_delta_value = delta_y / plot.height() * y_span
                y_axis.setRange(y_axis.min() + y_delta_value, y_axis.max() + y_delta_value)
            self._manual_view = True
            self._last_x = event.position().x()
            self._last_y = event.position().y()
            self.view_changed.emit()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def reset_view(self, sample_count: int = 0) -> None:
        self._manual_view = False
        self._set_auto_ranges(sample_count)
        self.view_changed.emit()

    def update_live_range(self, latest_time: float) -> None:
        self._set_auto_ranges(latest_time)
        self.view_changed.emit()

    def set_fixed_y_range(self, minimum: float, maximum: float) -> None:
        self._fixed_y_range = (minimum, maximum)
        axis = self._y_axis()
        if axis is not None:
            axis.setRange(minimum, maximum)

    def _set_auto_ranges(self, latest_time: float) -> None:
        x_axis = self._x_axis()
        y_axis = self._y_axis()
        if x_axis is not None:
            span = max(x_axis.max() - x_axis.min(), 10.0)
            latest = max(float(latest_time), 0.0)
            if latest <= span:
                x_axis.setRange(0, span)
            else:
                x_axis.setRange(latest - span, latest)
        if y_axis is None:
            return
        if self._fixed_y_range is not None:
            y_axis.setRange(*self._fixed_y_range)
            return
        values = []
        for series in self.chart().series():
            points = getattr(series, "pointsVector", lambda: [])()
            values.extend(point.y() for point in points)
        if not values:
            y_axis.setRange(0, 1)
            return
        minimum = min(values)
        maximum = max(values)
        span = max(maximum - minimum, max(abs(minimum), abs(maximum), 1.0) * 0.05)
        padding = span * 0.12
        y_axis.setRange(minimum - padding, maximum + padding)


class OscilloscopeDialog(QDialog):
    def __init__(
        self,
        raw_chart_view: OscilloscopeChartView,
        ratio_chart_view: OscilloscopeChartView,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("实时曲线")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(700, 500)
        self.resize(980, 760)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("实时曲线"))
        toolbar.addStretch()
        self.fullscreen_button = QPushButton("全屏")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        toolbar.addWidget(self.fullscreen_button)
        layout.addLayout(toolbar)
        layout.addWidget(raw_chart_view, 1)
        layout.addWidget(ratio_chart_view, 1)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setText("全屏")
        else:
            self.showFullScreen()
            self.fullscreen_button.setText("退出全屏")


class FaradayOperationPage(QWidget):
    page_id = "run"
    title = "实验采集"
    compact_page = True

    def __init__(self, project: ExperimentProject, controller: FaradayController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.project = project
        self.controller = controller
        self._current_wavelength: str | None = None
        self._debugging = False
        self._collect_stop_requested = False
        self._sample_count = 0
        self._anomaly_count = 0
        self._live_started_at = 0.0

        self.wavelength = QComboBox()
        self.wavelength.addItem("请选择波长", "")
        for item in project.plugin_config.get("wavelengths", []):
            self.wavelength.addItem(f"{float(item['value_nm']):g} nm", str(item["id"]))
        self.confirm_wavelength = QPushButton("确定波长")
        self.confirm_wavelength.clicked.connect(self._select_wavelength)
        self.message = QLabel("点击页面下方“开始采集”进入设备会话，然后选择波长。")
        self.message.setObjectName("muted")

        self.points = QTableWidget(0, 6)
        self.points.setHorizontalHeaderLabels(["序号", "I(A)", "B(mT)", "R", "θ(rad)", "状态"])
        self.points.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.points.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.points.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.points.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.points.setColumnWidth(0, 42)
        self.points.setColumnWidth(3, 64)
        self.points.setMinimumHeight(96)
        self.points.setMaximumHeight(220)
        self.points.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._fill_points()

        self.debug_button = QPushButton("调试光路")
        self.stop_debug_button = QPushButton("结束调试")
        self.collect_button = QPushButton("开始采集")
        self.points.itemSelectionChanged.connect(self._refresh_collect_button)
        self.reset_chart_button = QPushButton("重置视图")
        self.show_chart_button = QPushButton("打开实时曲线")
        self.debug_button.clicked.connect(self._start_debug_selected)
        self.stop_debug_button.clicked.connect(self.controller.stop_debug)
        self.collect_button.clicked.connect(self._collect_selected)
        self.reset_chart_button.clicked.connect(self._reset_chart_view)
        self.show_chart_button.clicked.connect(self._show_chart)
        self._set_action_state(False, False)

        self.samples_per_point = max(1, int(project.plugin_config.get("serial", {}).get("samples_per_point", 1)))
        self.progress = QProgressBar()
        self.progress.setRange(0, self.samples_per_point)
        self.progress.setFormat("%v / %m")
        self.progress.setValue(0)

        self.left_series = QLineSeries()
        self.left_series.setName("raw_left")
        self.right_series = QLineSeries()
        self.right_series.setName("raw_right")
        raw_chart = QChart()
        raw_chart.addSeries(self.left_series)
        raw_chart.addSeries(self.right_series)
        self._configure_chart(raw_chart, "raw_left / raw_right")
        self.raw_chart_view = OscilloscopeChartView(raw_chart)
        self.raw_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.r_series = QLineSeries()
        self.r_series.setName("R")
        self.r_reference_series = QLineSeries()
        self.r_reference_series.setName("R = 1")
        self.r_reference_series.setPen(QPen(QColor("#e53935"), 2, Qt.PenStyle.SolidLine))
        self.r_reference_series.append(0.0, 1.0)
        self.r_reference_series.append(1.0, 1.0)
        ratio_chart = QChart()
        ratio_chart.addSeries(self.r_series)
        ratio_chart.addSeries(self.r_reference_series)
        self._configure_chart(ratio_chart, "R", show_y_axis=True, y_range=(0.0, 2.0))
        self.r_chart_view = OscilloscopeChartView(ratio_chart)
        self.r_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.r_chart_view.set_fixed_y_range(0.0, 2.0)
        self.r_chart_view.view_changed.connect(self._sync_reference_line_to_view)
        self._sync_reference_line_to_view()
        self.chart_dialog = OscilloscopeDialog(self.raw_chart_view, self.r_chart_view, self)

        top = QHBoxLayout()
        top.addWidget(QLabel("实验波长"))
        top.addWidget(self.wavelength)
        top.addWidget(self.confirm_wavelength)
        top.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(6)
        for button in (
            self.debug_button,
            self.stop_debug_button,
            self.collect_button,
            self.reset_chart_button,
            self.show_chart_button,
        ):
            button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(button, 1)

        right = QVBoxLayout()
        right.addLayout(top)
        right.addWidget(self.message)
        right.addWidget(self.points, 1)
        right.addLayout(actions)
        right.addWidget(QLabel("当前磁场点采集进度"))
        right.addWidget(self.progress)

        self.live_values = QTableWidget(0, 3)
        self.live_values.setHorizontalHeaderLabels(["左路", "右路", "R"])
        self.live_values.horizontalHeaderItem(0).setToolTip("左路原始数据（raw_left）")
        self.live_values.horizontalHeaderItem(1).setToolTip("右路原始数据（raw_right）")
        self.live_values.horizontalHeaderItem(2).setToolTip("比值 R")
        self.live_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.live_values.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.live_values.setAlternatingRowColors(True)
        self.live_values.verticalHeader().setVisible(False)
        self.live_values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.live_values.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.live_values.setMinimumWidth(0)
        self.live_values.setMinimumHeight(0)
        self.live_values.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.live_values.verticalHeader().setDefaultSectionSize(30)
        self.live_values.setStyleSheet(
            "QTableWidget { background: #111c25; color: #ffffff; border: 1px solid #3f5d70; "
            "font-family: Consolas, monospace; font-size: 16px; }"
            "QHeaderView::section { background: #203644; color: #ffffff; padding: 6px; border: 0; }"
            "QScrollBar:vertical { width: 14px; background: #0c141c; }"
            "QScrollBar::handle:vertical { background: #3f5d70; min-height: 24px; border-radius: 6px; }"
        )
        live_box = QGroupBox("串口实时数据")
        live_box.setMinimumSize(220, 0)
        live_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        live_layout = QVBoxLayout(live_box)
        live_header = QHBoxLayout()
        live_header.addWidget(QLabel("历史数据"))
        live_header.addStretch()
        self.live_anomaly_label = QLabel("异常：0")
        self.live_anomaly_label.setStyleSheet("color: #b42318; font-weight: 700;")
        live_header.addWidget(self.live_anomaly_label)
        self.live_position = QLabel("历史位置：0 / 0")
        self.live_position.setObjectName("muted")
        live_header.addWidget(self.live_position)
        live_layout.addLayout(live_header)
        live_layout.addWidget(self.live_values)

        operation_box = QGroupBox("实验操作")
        operation_box.setMinimumSize(0, 0)
        operation_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        operation_box.setLayout(right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.addWidget(live_box)
        self.splitter.addWidget(operation_box)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.splitter, 1)

        controller.sample_received.connect(self._on_sample)
        controller.point_changed.connect(self._on_point_changed)
        controller.session_ready.connect(lambda: self._set_action_state(True, False))
        controller.session_message.connect(self.message.setText)
        self.live_values.verticalScrollBar().valueChanged.connect(self._update_live_position)
        self._update_live_position()

    @staticmethod
    def _configure_chart(
        chart: QChart,
        title: str,
        *,
        show_y_axis: bool = False,
        y_range: tuple[float, float] | None = None,
    ) -> None:
        chart.setTitle(title)
        chart.createDefaultAxes()
        x_axis = chart.axisX()
        y_axis = chart.axisY()
        if isinstance(x_axis, QValueAxis):
            x_axis.setTitleText("时间 (s)")
        if isinstance(y_axis, QValueAxis):
            if y_range is not None:
                y_axis.setRange(*y_range)
                y_axis.setTickCount(11)
                y_axis.setMinorTickCount(19)
                y_axis.setLabelFormat("%.1f")
            y_axis.setLabelsVisible(show_y_axis)
            y_axis.setGridLineVisible(show_y_axis)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_configuration()

    def refresh_configuration(self) -> None:
        """Reload values saved by the configuration page after page creation."""
        selected_id = str(self.wavelength.currentData() or "")
        self.wavelength.blockSignals(True)
        self.wavelength.clear()
        self.wavelength.addItem("请选择波长", "")
        for item in self.project.plugin_config.get("wavelengths", []):
            self.wavelength.addItem(f"{float(item['value_nm']):g} nm", str(item["id"]))
        index = self.wavelength.findData(selected_id)
        self.wavelength.setCurrentIndex(index if index >= 0 else 0)
        self.wavelength.blockSignals(False)
        self._fill_points()
        active_wavelength = self._current_wavelength or selected_id
        if active_wavelength:
            self._refresh_points_from_controller(active_wavelength)
        self.samples_per_point = max(1, int(self.project.plugin_config.get("serial", {}).get("samples_per_point", 1)))
        self.progress.setRange(0, self.samples_per_point)
        self.progress.setValue(0)

    def _fill_points(self) -> None:
        self.points.setRowCount(0)
        for index, point in enumerate(self.project.plugin_config.get("field_points", []), start=1):
            self.points.insertRow(index - 1)
            self.points.setItem(index - 1, 0, QTableWidgetItem(str(index)))
            self.points.setItem(index - 1, 1, QTableWidgetItem(f"{float(point['current_a']):g}"))
            magnetic_field_mt = float(point["magnetic_field_t"]) * 1000.0
            self.points.setItem(index - 1, 2, QTableWidgetItem(f"{magnetic_field_mt:g}"))
            self.points.setItem(index - 1, 3, QTableWidgetItem("--"))
            self.points.setItem(index - 1, 4, QTableWidgetItem("--"))
            self.points.setItem(index - 1, 5, QTableWidgetItem("等待"))

    def _set_action_state(self, enabled: bool, debugging: bool) -> None:
        self.debug_button.setEnabled(enabled and not debugging)
        self.stop_debug_button.setEnabled(enabled and debugging)
        collecting = self._selected_point_status() == "采集中"
        self.points.setEnabled(not collecting)
        self.collect_button.setEnabled(
            enabled
            and not debugging
            and self._current_wavelength is not None
            and not self._collect_stop_requested
        )
        self.confirm_wavelength.setEnabled(enabled)
        self.wavelength.setEnabled(enabled)
        self._refresh_collect_button()

    def _selected_point_status(self) -> str:
        row = self.points.currentRow()
        status_item = self.points.item(row, 5) if row >= 0 else None
        return status_item.text() if status_item is not None else ""

    def _refresh_collect_button(self) -> None:
        status = self._selected_point_status()
        if status == "采集中":
            self.collect_button.setText("停止采集")
        elif status == "完成":
            self.collect_button.setText("重新采集")
        else:
            self.collect_button.setText("开始采集")

    def _select_wavelength(self) -> None:
        wavelength_id = str(self.wavelength.currentData() or "")
        if not wavelength_id:
            self.message.setText("请选择一个波长。")
            return
        self._current_wavelength = wavelength_id
        self.controller.select_wavelength(wavelength_id)
        self._clear_chart()
        self._refresh_points_from_controller(wavelength_id)
        self._set_action_state(True, False)
        self.message.setText("波长已确认，请选择磁场点进行调试或采集。")

    def _collect_selected(self) -> None:
        if self._current_wavelength is None:
            return
        row = self.points.currentRow()
        if row < 0:
            self.message.setText("请先选择一个磁场点。")
            return
        if self._selected_point_status() == "采集中":
            self._collect_stop_requested = True
            self.collect_button.setEnabled(False)
            self.message.setText("正在停止当前磁场点采集...")
            self.controller.stop_collect()
            return
        point_config = self.project.plugin_config.get("field_points", [])[row]
        self._collect_stop_requested = False
        self._clear_chart()
        self._show_chart()
        self.controller.collect_point(str(point_config["id"]))

    def _start_debug_selected(self) -> None:
        if self._current_wavelength is None:
            return
        row = self.points.currentRow()
        if row < 0:
            self.message.setText("请先选择一个磁场点。")
            return
        point_config = self.project.plugin_config.get("field_points", [])[row]
        self._clear_chart()
        self._show_chart()
        self.controller.start_debug(str(point_config["id"]))

    def _clear_chart(self) -> None:
        self.left_series.clear()
        self.right_series.clear()
        self.r_series.clear()
        self._sample_count = 0
        self._live_started_at = time.monotonic()
        self.live_values.setRowCount(0)
        self.progress.setValue(0)
        self._anomaly_count = 0
        self.live_anomaly_label.setText("异常：0")
        self._update_live_position()
        self.raw_chart_view.reset_view()
        self.r_chart_view.reset_view()
        self._sync_reference_line_to_view()

    def _set_reference_line(self, minimum: float, maximum: float) -> None:
        self.r_reference_series.clear()
        self.r_reference_series.append(float(minimum), 1.0)
        self.r_reference_series.append(float(maximum), 1.0)

    def _sync_reference_line_to_view(self) -> None:
        axis = self.r_chart_view.chart().axisX()
        if isinstance(axis, QValueAxis):
            self._set_reference_line(axis.min(), axis.max())

    def _reset_chart_view(self) -> None:
        elapsed = time.monotonic() - self._live_started_at if self._live_started_at else 0.0
        self.raw_chart_view.reset_view(elapsed)
        self.r_chart_view.reset_view(elapsed)
        self._sync_reference_line_to_view()

    def _show_chart(self) -> None:
        self.chart_dialog.show()
        self.chart_dialog.raise_()
        self.chart_dialog.activateWindow()

    def _refresh_points_from_controller(self, wavelength_id: str) -> None:
        wavelength = self.controller._data.get(wavelength_id)
        if wavelength is None:
            return
        for point in wavelength["points"]:
            row = int(point["index"]) - 1
            if row >= self.points.rowCount():
                continue
            self.points.setItem(row, 3, QTableWidgetItem(f"{float(point['r']):g}" if "r" in point else "--"))
            self.points.setItem(row, 4, QTableWidgetItem(f"{float(point.get('theta_rad', 0.0)):g}" if "theta_rad" in point else "--"))
            status = {"waiting": "等待", "debugging": "调试中", "collecting": "采集中", "complete": "完成"}.get(str(point.get("status")), str(point.get("status")))
            self.points.setItem(row, 5, QTableWidgetItem(status))

    def _on_sample(self, sample: dict[str, Any]) -> None:
        if sample.get("wavelength_id") != self._current_wavelength:
            return
        if not self._live_started_at:
            self._live_started_at = time.monotonic()
        elapsed = time.monotonic() - self._live_started_at
        valid = bool(sample.get("valid", True))
        raw_left = self._safe_float(sample.get("raw_left"))
        raw_right = self._safe_float(sample.get("raw_right"))
        ratio = self._safe_float(sample.get("r"))
        if valid and raw_left is not None and raw_right is not None and ratio is not None:
            self._sample_count += 1
            self.progress.setValue(min(self._sample_count, self.samples_per_point))
            self.left_series.append(elapsed, raw_left)
            self.right_series.append(elapsed, raw_right)
            self.r_series.append(elapsed, ratio)
        scroll_bar = self.live_values.verticalScrollBar()
        follow_latest = scroll_bar.value() >= scroll_bar.maximum() - 2
        row = self.live_values.rowCount()
        self.live_values.insertRow(row)
        values = (
            f"{raw_left:.3f}" if raw_left is not None else "--",
            f"{raw_right:.3f}" if raw_right is not None else "--",
            f"{ratio:.6f}" if ratio is not None and valid else ("--" if not valid else "异常"),
        )
        row_items = [QTableWidgetItem(value) for value in values]
        for column, item in enumerate(row_items):
            self.live_values.setItem(row, column, item)
        if not valid:
            self._anomaly_count += 1
            self.live_anomaly_label.setText(f"异常：{self._anomaly_count}")
            reason = str(sample.get("reason", "未知异常"))
            self.message.setText(f"检测到异常样本：{reason}，5秒内等待正常值")
            for item in row_items:
                item.setBackground(QBrush(QColor("#5f2b2b")))
                item.setForeground(QBrush(QColor("#ffd7d7")))
                item.setToolTip(reason)
        if follow_latest:
            self.live_values.scrollToBottom()
        self._update_live_position()
        if sample.get("debug"):
            self._debugging = True
            self._set_action_state(True, True)
        self.raw_chart_view.update_live_range(elapsed)
        self.r_chart_view.update_live_range(elapsed)
        self._sync_reference_line_to_view()

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _update_live_position(self) -> None:
        total = self.live_values.rowCount()
        if total <= 0:
            self.live_position.setText("历史位置：0 / 0")
            return
        current = self.live_values.verticalScrollBar().value() + 1
        current = min(max(current, 1), total)
        self.live_position.setText(f"历史位置：{current} / {total}")

    def _on_point_changed(self, point: dict[str, Any]) -> None:
        if point.get("wavelength_id") != self._current_wavelength:
            return
        row = int(point["index"]) - 1
        if row < 0 or row >= self.points.rowCount():
            return
        self.points.setItem(row, 3, QTableWidgetItem(f"{float(point.get('r', 0.0)):g}" if "r" in point else "--"))
        self.points.setItem(row, 4, QTableWidgetItem(f"{float(point.get('theta_rad', 0.0)):g}" if "theta_rad" in point else "--"))
        status = {"waiting": "等待", "debugging": "调试中", "collecting": "采集中", "complete": "完成"}.get(str(point.get("status")), str(point.get("status")))
        self.points.setItem(row, 5, QTableWidgetItem(status))
        self._debugging = status == "调试中"
        if status != "采集中":
            self._collect_stop_requested = False
        self._set_action_state(True, self._debugging)
