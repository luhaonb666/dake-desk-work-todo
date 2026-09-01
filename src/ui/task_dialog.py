"""Task editor with calendar dates, 15-minute times and deliberate Enter handling."""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QPlainTextEdit, QTextEdit, QVBoxLayout,
)


class TitleEditor(QPlainTextEdit):
    confirmed = pyqtSignal()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                self.insertPlainText("\n")
            else:
                self.confirmed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class TaskDialog(QDialog):
    def __init__(self, task=None, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("编辑事项" if task else "添加事项")
        self.setMinimumWidth(470)
        self.setStyleSheet(
            """
            QDialog { background:#fbf9ff; color:#4b4658; }
            QLabel { color:#5f586e; }
            QPlainTextEdit, QTextEdit, QDateEdit, QComboBox {
                background:#ffffff; border:1px solid #e2d9f0; border-radius:11px;
                padding:7px; selection-background-color:#cdbdec;
            }
            QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus, QComboBox:focus {
                border:2px solid #ab93dc;
            }
            QPushButton { background:#ffffff; border:1px solid #ddd3ed; border-radius:11px; padding:7px 14px; }
            QPushButton:hover { background:#f2edfc; }
            """
        )
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = TitleEditor()
        self.title_edit.setPlainText(task["title"] if task else "")
        self.title_edit.setPlaceholderText("例如：xxxx公司的技术方案")
        self.title_edit.setFixedHeight(76)
        self.title_hint = QLabel("Enter 确认当前文字；Shift + Enter 或 Alt + Enter 换行。保存按钮才会创建事项。")
        self.title_hint.setStyleSheet("font-size:11px; color:#9299a5;")
        self.title_edit.confirmed.connect(lambda: self.title_hint.setText("当前文字已确认；请继续编辑或点击保存。"))
        title_box = QVBoxLayout()
        title_box.addWidget(self.title_edit)
        title_box.addWidget(self.title_hint)

        self.notes_edit = QTextEdit(task["notes"] if task else "")
        self.notes_edit.setPlaceholderText("可补充说明、材料或下一步")
        self.notes_edit.setFixedHeight(100)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy 年 MM 月 dd 日")
        selected = QDate.fromString(task["task_date"], "yyyy-MM-dd") if task else QDate.currentDate()
        self.date_edit.setDate(selected)

        self.time_combo = QComboBox()
        self.time_combo.addItem("无具体时间", None)
        for hour in range(24):
            for minute in range(0, 60, 15):
                text = f"{hour:02d}:{minute:02d}"
                self.time_combo.addItem(text, text)
        if task and task["due_time"]:
            index = self.time_combo.findData(task["due_time"])
            self.time_combo.setCurrentIndex(index if index >= 0 else 0)
        self.fixed_check = QCheckBox("固定待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        form.addRow("事项", title_box)
        form.addRow("说明", self.notes_edit)
        form.addRow("日期", self.date_edit)
        form.addRow("时间", self.time_combo)
        form.addRow("", self.fixed_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "title": self.title_edit.toPlainText().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_time": self.time_combo.currentData(),
            "is_fixed": self.fixed_check.isChecked(),
        }

    def accept(self) -> None:
        if self.title_edit.toPlainText().strip():
            super().accept()
        else:
            self.title_edit.setFocus()
