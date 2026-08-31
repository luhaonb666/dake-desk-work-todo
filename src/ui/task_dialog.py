"""Task editor dialog; all text entry stays in the editor window."""

from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)


class TaskDialog(QDialog):
    def __init__(self, task=None, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("编辑事项" if task else "添加事项")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit(task["title"] if task else "")
        self.title_edit.setPlaceholderText("例如：完成周报")
        self.notes_edit = QTextEdit(task["notes"] if task else "")
        self.notes_edit.setPlaceholderText("可补充说明、材料或下一步")
        self.notes_edit.setFixedHeight(110)

        self.day_combo = QComboBox()
        today = date.today()
        self.day_combo.addItem(f"今天（{today:%m月%d日}）", today.isoformat())
        tomorrow = today + timedelta(days=1)
        self.day_combo.addItem(f"明天（{tomorrow:%m月%d日}）", tomorrow.isoformat())
        if task and task["task_date"] == tomorrow.isoformat():
            self.day_combo.setCurrentIndex(1)

        self.has_time = QCheckBox("设置具体时间")
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime())
        if task and task["due_time"]:
            self.has_time.setChecked(True)
            self.time_edit.setTime(QTime.fromString(task["due_time"], "HH:mm"))
        self.time_edit.setEnabled(self.has_time.isChecked())
        self.has_time.toggled.connect(self.time_edit.setEnabled)

        self.fixed_check = QCheckBox("固定待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        form.addRow("事项", self.title_edit)
        form.addRow("说明", self.notes_edit)
        form.addRow("日期", self.day_combo)
        form.addRow("时间", self.has_time)
        form.addRow("", self.time_edit)
        form.addRow("", self.fixed_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "task_date": self.day_combo.currentData(),
            "due_time": self.time_edit.time().toString("HH:mm") if self.has_time.isChecked() else None,
            "is_fixed": self.fixed_check.isChecked(),
        }

    def accept(self) -> None:
        if self.title_edit.text().strip():
            super().accept()
        else:
            self.title_edit.setFocus()
