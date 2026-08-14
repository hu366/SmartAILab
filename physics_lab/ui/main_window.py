from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from physics_lab.core.contracts import ExperimentProject, GeneralConfig, PlatformServices, WorkflowWorker, today_string
from physics_lab.core.cancellation import CancellationToken
from physics_lab.core.project_logger import ProjectLogger
from physics_lab.core.plugin_manager import PluginManager
from physics_lab.core.project_repository import ProjectRepository
from physics_lab.ui.styles import APP_STYLE
from physics_lab.ui.log_dialog import LogDialog


class Worker(QObject):
    progress = Signal(int, str)
    completed = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, workflow, project: ExperimentProject) -> None:
        super().__init__()
        self.workflow = workflow
        self.project = project
        self._control = CancellationToken()

    def cancel(self) -> None:
        self._control.cancel()

    def is_cancelled(self) -> bool:
        return self._control.is_cancelled()

    def pause(self) -> None:
        self._control.pause()

    def resume(self) -> None:
        self._control.resume()

    def is_paused(self) -> bool:
        return self._control.is_paused()

    def wait_until_resumed(self) -> None:
        self._control.wait_until_resumed()

    def run(self) -> None:
        try:
            self.workflow.run(self)
        except Exception as exc:  # Keep device and plugin failures inside the UI error path.
            self.failed.emit(str(exc))


class EmptyPage(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 44, 48, 44)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()


class PluginCard(QFrame):
    selected = Signal(str)

    def __init__(self, plugin) -> None:
        super().__init__()
        self.plugin_id = plugin.plugin_id
        self.setObjectName("pluginCard")
        layout = QVBoxLayout(self)
        icon = QLabel(plugin.icon)
        icon.setStyleSheet("font-size: 30px; color: #216bb1;")
        name = QLabel(plugin.display_name)
        name.setStyleSheet("font-size: 17px; font-weight: 700;")
        description = QLabel(plugin.description)
        description.setObjectName("muted")
        description.setWordWrap(True)
        button = QPushButton("选择此实验")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self.selected.emit(self.plugin_id))
        layout.addWidget(icon)
        layout.addWidget(name)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)


class NewExperimentPage(QWidget):
    plugin_selected = Signal(str)

    def __init__(self, plugins: list, plugin_issues: list | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 44, 48, 44)
        title = QLabel("新实验")
        title.setObjectName("pageTitle")
        subtitle = QLabel("选择一个实验插件开始创建实验项目")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        if plugin_issues:
            issues = QLabel("部分实验插件未加载：\n" + "\n".join(
                f"- {issue.plugin_directory}: {issue.message}" for issue in plugin_issues
            ))
            issues.setWordWrap(True)
            issues.setStyleSheet("color: #a33a32; background: #fff3f1; padding: 10px; border-radius: 5px;")
            layout.addWidget(issues)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        for plugin in plugins:
            card = PluginCard(plugin)
            card.selected.connect(self.plugin_selected)
            cards.addWidget(card)
        cards.addStretch()
        layout.addLayout(cards)
        layout.addStretch()


class GeneralConfigPage(QWidget):
    submitted = Signal(object)
    cancelled = Signal()

    def __init__(self, plugin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plugin = plugin
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 44, 48, 44)
        title = QLabel("通用配置")
        title.setObjectName("pageTitle")
        subtitle = QLabel(f"正在创建：{plugin.display_name}")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_box = QFrame()
        form_box.setObjectName("formBox")
        form = QFormLayout(form_box)
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如：重力加速度测量")
        self.number = QLineEdit()
        self.number.setPlaceholderText("例如：2026-001")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(self.date.minimumDate().currentDate())
        form.addRow("实验名称", self.name)
        form.addRow("实验编号", self.number)
        form.addRow("实验日期", self.date)
        layout.addWidget(form_box)

        actions = QHBoxLayout()
        back = QPushButton("返回")
        next_button = QPushButton("创建并进入实验")
        next_button.setObjectName("primary")
        back.clicked.connect(self.cancelled)
        next_button.clicked.connect(self.submit)
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(next_button)
        layout.addLayout(actions)
        layout.addStretch()

    def submit(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "配置不完整", "请输入实验名称。")
            self.name.setFocus()
            return
        if not self.number.text().strip():
            QMessageBox.warning(self, "配置不完整", "请输入实验编号。")
            self.number.setFocus()
            return
        config = GeneralConfig(self.name.text().strip(), self.number.text().strip(), self.date.date().toString("yyyy-MM-dd"))
        self.submitted.emit(config)


class WorkflowPage(QWidget):
    def __init__(self, repository: ProjectRepository, plugin, project: ExperimentProject, services: PlatformServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.plugin = plugin
        self.project = project
        self.logger = ProjectLogger(repository, project)
        self.workflow = plugin.create_workflow(project, services)
        self.page_ids = self.workflow.page_ids()
        self.index = 0
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.run_terminal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 34, 48, 34)
        heading = QHBoxLayout()
        self.title = QLabel(self.workflow.page_title(self.page_ids[0]))
        self.title.setObjectName("pageTitle")
        self.status = QLabel("草稿")
        self.status.setObjectName("muted")
        heading.addWidget(self.title)
        heading.addStretch()
        heading.addWidget(self.status)
        layout.addLayout(heading)

        self.progress = QLabel()
        self.progress.setObjectName("muted")
        layout.addWidget(self.progress)
        self.stack = QStackedWidget()
        for page_id in self.page_ids:
            self.stack.addWidget(self.workflow.create_page(page_id, self))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.stack)
        layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.back_button = QPushButton("上一步")
        self.pause_button = QPushButton("暂停实验")
        self.pause_button.setVisible(False)
        self.cancel_button = QPushButton("取消实验")
        self.log_button = QPushButton("查看日志")
        self.cancel_button.setVisible(False)
        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("primary")
        self.back_button.clicked.connect(self.previous)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.cancel_button.clicked.connect(self.cancel_run)
        self.log_button.clicked.connect(self.show_logs)
        self.next_button.clicked.connect(self.next)
        actions.addWidget(self.back_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.log_button)
        actions.addStretch()
        actions.addWidget(self.next_button)
        layout.addLayout(actions)
        self.refresh_controls()

    def refresh_controls(self) -> None:
        self.title.setText(self.workflow.page_title(self.page_ids[self.index]))
        self.progress.setText(f"步骤 {self.index + 1} / {len(self.page_ids)}")
        self.back_button.setEnabled(self.index > 0 and self.thread is None)
        self.next_button.setEnabled(self.thread is None)
        self.cancel_button.setVisible(self.thread is not None and not self.run_terminal)
        self.cancel_button.setEnabled(
            self.thread is not None
            and not self.run_terminal
            and self.worker is not None
            and not self.worker.is_cancelled()
        )
        self.pause_button.setVisible(self.thread is not None and not self.run_terminal)
        self.pause_button.setEnabled(self.thread is not None and not self.run_terminal)
        if self.worker is not None:
            self.pause_button.setText("继续实验" if self.worker.is_paused() else "暂停实验")
        if self.page_ids[self.index] == "run":
            self.next_button.setText("重新连接并采集" if self.project.status == "failed" else "开始采集")
        else:
            self.next_button.setText("完成实验" if self.index == len(self.page_ids) - 1 else "下一步")

    def previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.stack.setCurrentIndex(self.index)
            self.refresh_controls()

    def next(self) -> None:
        page_id = self.page_ids[self.index]
        if not self.persist_current_page():
            return
        if page_id == "run":
            self.start_run()
            return
        if self.index < len(self.page_ids) - 1:
            self.index += 1
            self.stack.setCurrentIndex(self.index)
            self.refresh_controls()
            return
        self.project.status = "completed"
        self.project.current_step = "result"
        self.repository.save(self.project)
        self.status.setText("已完成")

    def show_logs(self) -> None:
        LogDialog(self.logger, self).exec()

    def persist_current_page(self) -> bool:
        page = self.stack.currentWidget()
        validate = getattr(page, "validate", None)
        if callable(validate):
            valid, message = validate()
            if not valid:
                QMessageBox.warning(self, "配置不完整", message)
                return False
        save_to_project = getattr(page, "save_to_project", None)
        if callable(save_to_project):
            save_to_project(self.project)
            self.repository.save(self.project)
        return True

    def start_run(self) -> None:
        self.run_terminal = False
        self.project.status = "running"
        self.project.current_step = "run"
        self.repository.save(self.project)
        self.logger.info("experiment_started", "开始执行实验", plugin_id=self.plugin.plugin_id)
        self.status.setText("实验进行中")
        self.thread = QThread(self)
        self.worker = Worker(self.workflow, self.project)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(lambda value, message: self.progress.setText(f"{message} · {value}%"))
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.start()
        self.refresh_controls()

    def cancel_run(self) -> None:
        if self.worker is not None and not self.run_terminal:
            self.worker.cancel()
            self.logger.warning("experiment_cancel_requested", "操作员请求取消实验")
            self.status.setText("正在取消实验")
            self.progress.setText("正在停止采集并释放设备...")
            self.refresh_controls()

    def toggle_pause(self) -> None:
        if self.worker is None or self.run_terminal:
            return
        if self.worker.is_paused():
            self.worker.resume()
            self.status.setText("实验进行中")
            self.progress.setText("正在继续采集...")
        else:
            self.worker.pause()
            self.status.setText("实验已暂停")
            self.progress.setText("已暂停，等待继续...")
        self.refresh_controls()

    def on_completed(self, result: dict) -> None:
        self.run_terminal = True
        self.project.result = result
        self.project.status = "completed"
        self.project.current_step = "result"
        self.repository.save(self.project)
        self.status.setText("采集完成")
        self.logger.info("experiment_completed", "实验采集完成", result=result)
        if self.index < len(self.page_ids) - 1:
            self.index += 1
            self.stack.setCurrentIndex(self.index)
        result_page = self.workflow.pages.get("result")
        if result_page is not None and hasattr(result_page, "refresh"):
            result_page.refresh()

    def on_failed(self, message: str) -> None:
        self.run_terminal = True
        self.project.status = "failed"
        self.repository.save(self.project)
        self.logger.error("experiment_failed", message)
        self.status.setText("设备连接或实验失败")
        QMessageBox.critical(self, "实验失败，可重试", f"{message}\n\n点击“重新连接并采集”可以再次尝试。")

    def on_cancelled(self) -> None:
        if self.run_terminal:
            return
        self.run_terminal = True
        self.project.status = "cancelled"
        self.project.current_step = self.page_ids[self.index]
        self.repository.save(self.project)
        self.logger.warning("experiment_cancelled", "实验已取消")
        self.status.setText("实验已取消")

    def on_thread_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.refresh_controls()


class MainWindow(QMainWindow):
    def __init__(self, repository: ProjectRepository, plugin_manager: PluginManager, services: PlatformServices) -> None:
        super().__init__()
        self.repository = repository
        self.plugin_manager = plugin_manager
        self.services = services
        self.current_workflow: WorkflowPage | None = None
        self.setWindowTitle("Physics Lab")
        self.resize(1180, 760)
        self.setStyleSheet(APP_STYLE)
        self.build_ui()
        self.show_history()

    def build_ui(self) -> None:
        shell = QWidget()
        shell.setObjectName("shell")
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(275)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 26, 22, 20)
        brand = QLabel("PHYSICS LAB")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addSpacing(22)
        self.new_button = QPushButton("＋  新实验")
        self.new_button.setObjectName("sidebarAction")
        self.new_button.clicked.connect(self.show_new_experiment)
        side.addWidget(self.new_button)
        label = QLabel("历史实验")
        label.setObjectName("eyebrow")
        side.addSpacing(25)
        side.addWidget(label)
        self.history = QListWidget()
        self.history.itemClicked.connect(self.open_history)
        side.addWidget(self.history, 1)
        footer = QLabel("本地项目存储")
        footer.setObjectName("eyebrow")
        side.addWidget(footer)
        root.addWidget(sidebar)
        self.content = QStackedWidget()
        root.addWidget(self.content, 1)
        self.setCentralWidget(shell)

    def show_history(self) -> None:
        self.history.clear()
        projects = self.repository.list_projects()
        for project in projects:
            item = QListWidgetItem(f"{project.general.name}\n{project.general.number} · {project.status}")
            item.setData(Qt.ItemDataRole.UserRole, project.project_id)
            self.history.addItem(item)
        if projects:
            self.show_welcome()
        else:
            self.show_new_experiment()

    def clear_content(self) -> None:
        while self.content.count():
            widget = self.content.widget(0)
            self.content.removeWidget(widget)
            widget.deleteLater()

    def show_welcome(self) -> None:
        self.clear_content()
        self.content.addWidget(EmptyPage("实验工作台", "从左侧新建实验，或打开一个历史实验项目。"))
        self.content.setCurrentIndex(0)

    def show_new_experiment(self) -> None:
        self.clear_content()
        page = NewExperimentPage(self.plugin_manager.all(), self.plugin_manager.issues)
        page.plugin_selected.connect(self.show_general_config)
        self.content.addWidget(page)
        self.content.setCurrentIndex(0)

    def show_general_config(self, plugin_id: str) -> None:
        plugin = self.plugin_manager.get(plugin_id)
        self.clear_content()
        page = GeneralConfigPage(plugin)
        page.submitted.connect(lambda config: self.create_project(plugin, config))
        page.cancelled.connect(self.show_new_experiment)
        self.content.addWidget(page)
        self.content.setCurrentIndex(0)

    def create_project(self, plugin, config: GeneralConfig) -> None:
        project = self.repository.create(plugin.plugin_id, plugin.version, config)
        self.show_history()
        self.open_project(plugin, project)

    def open_history(self, item: QListWidgetItem) -> None:
        project = self.repository.load(item.data(Qt.ItemDataRole.UserRole))
        try:
            plugin = self.plugin_manager.get(project.plugin_id)
        except KeyError:
            QMessageBox.warning(self, "插件不可用", f"找不到插件：{project.plugin_id}")
            return
        self.open_project(plugin, project)

    def open_project(self, plugin, project: ExperimentProject) -> None:
        self.clear_content()
        self.current_workflow = WorkflowPage(self.repository, plugin, project, self.services)
        self.content.addWidget(self.current_workflow)
        self.content.setCurrentIndex(0)
