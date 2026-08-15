from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QTextEdit


class LogDialog(QDialog):
    def __init__(self, logger, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("实验日志")
        self.resize(760, 520)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(logger.read_text())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(buttons)
