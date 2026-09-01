"""Task editor with deliberate keyboard behaviour and flexible time selection."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
)

from ui.theme import APP_STYLE


class TitleEditor(QPlainTextEdit):
    next_field_requested = pyqtSignal()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                self.insertPlainText("\n")
            else:
                self.next_field_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class TaskDialog(QDialog):
    def __init__(self, task=None, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.setObjectName("taskDialog")
        self.setWindowTitle("编辑事项" if task else "添加事项")
        self.setMinimumWidth(470)
        self.setStyleSheet(APP_STYLE + "QDialog#taskDialog { background:#f7f9fc; }")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = TitleEditor()
        self.title_edit.setPlainText(task["title"] if task else "")
        self.title_edit.setPlaceholderText("例如：xxxx公司的技术方案")
        self.title_edit.setFixedHeight(76)
        self.title_hint = QLabel("Enter 转到说明；Shift + Enter 或 Alt + Enter 在事项内换行；Ctrl + S 保存。")
        self.title_hint.setStyleSheet("font-size:11px; color:#9299a5;")
        title_box = QVBoxLayout()
        title_box.addWidget(self.title_edit)
        title_box.addWidget(self.title_hint)

        self.notes_edit = QTextEdit(task["notes"] if task else "")
        self.notes_edit.setPlaceholderText("可补充说明、材料或下一步")
        self.notes_edit.setFixedHeight(100)
        self.title_edit.next_field_requested.connect(self.notes_edit.setFocus)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy 年 MM 月 dd 日")
        selected = QDate.fromString(task["task_date"], "yyyy-MM-dd") if task else QDate.currentDate()
        self.date_edit.setDate(selected)

        self.time_enabled = QCheckBox("有具体时间")
        self.time_enabled.setChecked(bool(task and task["due_time"]))
        self.hour_combo = QComboBox()
        for hour in range(7, 23):
            self.hour_combo.addItem(f"{hour:02d} 时", hour)
        self.minute_combo = QComboBox()
        for minute in range(0, 60, 10):
            self.minute_combo.addItem(f"{minute:02d} 分", minute)
        if task and task["due_time"]:
            hour, minute = task["due_time"].split(":")
            self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(int(hour))))
            minute_index = self.minute_combo.findData(int(minute))
            # Existing V1.3 tasks may have a 15-minute value. Keep that exact
            # value when merely opening and saving the editor; new choices remain
            # on the V1.4 ten-minute grid.
            if minute_index < 0:
                self.minute_combo.addItem(f"{int(minute):02d} 分（原时间）", int(minute))
                minute_index = self.minute_combo.count() - 1
            self.minute_combo.setCurrentIndex(minute_index)
        else:
            next_hour = min(22, max(7, QTime.currentTime().hour() + 1))
            self.hour_combo.setCurrentIndex(self.hour_combo.findData(next_hour))
        self.hour_combo.activated.connect(lambda _: self.time_enabled.setChecked(True))
        self.minute_combo.activated.connect(lambda _: self.time_enabled.setChecked(True))
        time_box = QHBoxLayout()
        time_box.setContentsMargins(0, 0, 0, 0)
        time_box.addWidget(self.time_enabled)
        time_box.addWidget(self.hour_combo)
        time_box.addWidget(self.minute_combo)
        time_box.addStretch()

        self.fixed_check = QCheckBox("固定钉住待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        form.addRow("事项", title_box)
        form.addRow("说明", self.notes_edit)
        form.addRow("日期", self.date_edit)
        form.addRow("时间", time_box)
        form.addRow("", self.fixed_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.accept)

    def values(self) -> dict:
        due_time = None
        if self.time_enabled.isChecked():
            due_time = f"{self.hour_combo.currentData():02d}:{self.minute_combo.currentData():02d}"
        return {
            "title": self.title_edit.toPlainText().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_time": due_time,
            "is_fixed": self.fixed_check.isChecked(),
        }

    def accept(self) -> None:
        if not self.title_edit.toPlainText().strip():
            self.title_edit.setFocus()
            return
        if self.date_edit.date() < QDate.currentDate():
            answer = QMessageBox.question(
                self,
                "创建过去日期的待办",
                "是否新建在当前日期之前的待办？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()
