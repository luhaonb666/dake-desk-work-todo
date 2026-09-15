"""Task editor with deliberate keyboard behaviour and flexible time selection."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_HOURS, TIME_MINUTES, normalize_note_text
from ui.task_steps import TaskStepsEditor
from ui.theme import APP_STYLE


class TitleEditor(QPlainTextEdit):
    next_field_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._normalizing_lines = False
        self.textChanged.connect(self._keep_two_lines)

    def _keep_two_lines(self) -> None:
        if self._normalizing_lines:
            return
        text = self.toPlainText()
        lines = text.split("\n")
        if len(lines) <= 2:
            return
        # Keep pasted text instead of silently dropping it; only extra line
        # breaks are flattened into the second title line.
        normalized = lines[0] + "\n" + " ".join(part for part in lines[1:] if part)
        position = min(self.textCursor().position(), len(normalized))
        self._normalizing_lines = True
        self.setPlainText(normalized)
        cursor = self.textCursor()
        cursor.setPosition(position)
        self.setTextCursor(cursor)
        self._normalizing_lines = False

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                if self.document().blockCount() < 2:
                    self.insertPlainText("\n")
                else:
                    self.next_field_requested.emit()
            else:
                self.next_field_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PlainNotesEditor(QTextEdit):
    """Accept plain clipboard text only, so source formatting cannot add gaps."""

    def insertFromMimeData(self, source):  # noqa: N802
        if source.hasText():
            self.insertPlainText(normalize_note_text(source.text()))
            return
        super().insertFromMimeData(source)


class TaskDialog(QDialog):
    def __init__(self, task=None, parent=None, *, task_steps=None) -> None:
        super().__init__(parent)
        self.task = task
        self._last_imported_note_text: str | None = None
        self.setObjectName("taskDialog")
        self.setWindowTitle("编辑事项" if task else "添加事项")
        self.setMinimumWidth(470)
        self.setStyleSheet(APP_STYLE + "QDialog#taskDialog { background:#f7f9fc; }")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title_edit = TitleEditor()
        self.title_edit.setPlainText(task["title"] if task else "")
        self.title_edit.setPlaceholderText("例如：xxxx公司的技术方案")
        self.title_edit.setFixedHeight(64)
        self.title_hint = QLabel("事项标题最多2行；Enter 转到具体内容；Shift + Enter 或 Alt + Enter 换行；Ctrl + S 保存。")
        self.title_hint.setStyleSheet("font-size:11px; color:#9299a5;")
        title_box = QVBoxLayout()
        title_box.addWidget(self.title_edit)
        title_box.addWidget(self.title_hint)

        # QTextEdit's text-taking constructor treats the content as rich text
        # on some Qt builds. Set plain text explicitly so saved line breaks are
        # still line breaks when the same item is opened for editing again.
        self.notes_edit = PlainNotesEditor()
        self.notes_edit.setPlainText(normalize_note_text(task["notes"] if task else ""))
        self.notes_edit.setPlaceholderText("可填写具体内容、材料或下一步")
        self.notes_edit.setFixedHeight(100)
        self.notes_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title_edit.next_field_requested.connect(self.notes_edit.setFocus)
        self.steps_editor = TaskStepsEditor()
        self.steps_editor.set_steps(task_steps)
        self.notes_section = QFrame()
        notes_layout = QVBoxLayout(self.notes_section)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(3)
        notes_header = QHBoxLayout()
        notes_header.setContentsMargins(0, 0, 0, 0)
        notes_header.addStretch()
        self.import_steps_hint = QLabel("正文保留")
        self.import_steps_hint.setToolTip("把正文的每个非空行复制成一条待办步骤，原正文不会删除。")
        self.import_steps_hint.setStyleSheet("font-size:11px; color:#8b98aa; padding-right:4px;")
        notes_header.addWidget(self.import_steps_hint)
        self.import_steps_button = QPushButton("⇩ 按换行拆成步骤")
        self.import_steps_button.setObjectName("importStepsButton")
        self.import_steps_button.setToolTip("把正文中每个非空行各新增为一个待办步骤；原正文不会删除。")
        self.import_steps_button.setStyleSheet(
            "QPushButton#importStepsButton { color:#426ca8; background:#f7faff; border:1px solid #aebfe0; "
            "border-radius:7px; padding:4px 8px; font-size:12px; font-weight:600; }"
            "QPushButton#importStepsButton:hover { background:#eef4ff; border-color:#7597d1; }"
            "QPushButton#importStepsButton:disabled { color:#9ca9b9; background:#f7f9fc; border-color:#dce4ef; }"
        )
        notes_header.addWidget(self.import_steps_button)
        notes_layout.addLayout(notes_header)
        notes_layout.addWidget(self.notes_edit)
        self.import_steps_button.clicked.connect(self._import_note_lines)
        self.notes_edit.textChanged.connect(self._refresh_import_button)

        self.date_edit = CompactDatePicker()
        selected = QDate.fromString(task["task_date"], "yyyy-MM-dd") if task else QDate.currentDate()
        self.date_edit.setDate(selected)

        self.time_enabled = QCheckBox("有具体时间")
        self.time_enabled.setChecked(bool(task and task["due_time"]))
        # Keep the visible square in its own fixed-width control.  A normal
        # text-bearing QCheckBox retains platform-specific inner margins, which
        # made this indicator appear several pixels right of the other options.
        self.windows_reminder_check = QCheckBox()
        self.windows_reminder_check.setObjectName("windowsReminderIndicator")
        self.windows_reminder_check.setFixedSize(18, 18)
        task_supports_system_reminder = bool(task and "windows_reminder_enabled" in task.keys())
        self.windows_reminder_check.setChecked(
            bool(task and task_supports_system_reminder and task["windows_reminder_enabled"])
        )
        self.windows_reminder_check.setToolTip(
            "默认关闭。勾选后，到准点会显示软件内的置顶强提醒；Windows 通知可用时会作为额外提醒。"
        )
        self.windows_reminder_check.setStyleSheet(
            "QCheckBox#windowsReminderIndicator { padding:0; margin:0; border:none; background:transparent; }"
            "QCheckBox#windowsReminderIndicator::indicator { width:17px; height:17px; margin:0; }"
        )
        self.windows_reminder_label = QLabel("重要事项：准点强提醒（需手动关闭）")
        self.windows_reminder_label.setStyleSheet("color:#0659c9; font-weight:600; background:transparent;")
        self.windows_reminder_label.setToolTip(self.windows_reminder_check.toolTip())
        self.windows_reminder_box = QFrame()
        self.windows_reminder_box.setObjectName("windowsReminderBox")
        self.windows_reminder_box.setStyleSheet(
            "QFrame#windowsReminderBox { border:1px solid #b9ccff; border-radius:8px; background:#eef4ff; }"
        )
        reminder_layout = QHBoxLayout(self.windows_reminder_box)
        reminder_layout.setContentsMargins(0, 5, 7, 5)
        reminder_layout.setSpacing(8)
        reminder_layout.addWidget(self.windows_reminder_check)
        reminder_layout.addWidget(self.windows_reminder_label)
        reminder_layout.addStretch()
        self.hour_combo = NoWheelComboBox()
        for hour in TIME_HOURS:
            self.hour_combo.addItem(f"{hour:02d} 时", hour)
        self.minute_combo = NoWheelComboBox()
        for minute in TIME_MINUTES:
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
        self._sync_windows_reminder_availability(self.time_enabled.isChecked())
        self.time_enabled.toggled.connect(self._sync_windows_reminder_availability)

        self.fixed_check = QCheckBox("固定锁住待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        self.duplicate_check = QCheckBox("新增复制该条事项（保留原事项）")
        self.duplicate_check.setToolTip("复制会保留原事项并新建一条；若只是把旧事项改到今天，请在“之前未完成”中选择“移到今天”。")
        self.duplicate_check.setVisible(bool(task))
        self.duplicate_hint = QLabel("复制会保留原事项；旧事项只是改到今天，请在“之前未完成”中点“移到今天”。")
        self.duplicate_hint.setWordWrap(True)
        self.duplicate_hint.setStyleSheet("font-size:11px; color:#8793a2; padding-left:4px;")
        self.duplicate_hint.setVisible(bool(task))
        form.addRow("事项标题", title_box)
        form.addRow("", self.steps_editor)
        form.addRow("具体内容", self.notes_section)
        form.addRow("日期", self.date_edit)
        form.addRow("时间", time_box)
        form.addRow("", self.fixed_check)
        if task:
            form.addRow("", self.duplicate_check)
            form.addRow("", self.duplicate_hint)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color:#dbe4ee; margin:13px 0 8px;")
        form.addRow("", divider)
        # Important system push is a deliberate final choice rather than an
        # ordinary scheduling option, so it remains visually separate.
        form.addRow("", self.windows_reminder_box)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.accept)
        self._refresh_import_button()

    def _import_note_lines(self) -> None:
        text = self.notes_edit.toPlainText()
        imported = self.steps_editor.import_note_lines(text)
        if imported:
            self._last_imported_note_text = text
            self.import_steps_button.setText(f"已从正文新增 {imported} 个步骤")
            self._refresh_import_button()

    def _refresh_import_button(self) -> None:
        text = self.notes_edit.toPlainText()
        has_lines = bool([line for line in text.splitlines() if line.strip()])
        already_imported = text == self._last_imported_note_text
        self.import_steps_button.setEnabled(has_lines and not already_imported)
        if not has_lines:
            self.import_steps_button.setText("⇩ 按换行拆成步骤")
        elif already_imported:
            self.import_steps_button.setText("已拆成步骤（修改正文后可再导入）")

    def values(self) -> dict:
        due_time = None
        if self.time_enabled.isChecked():
            due_time = f"{self.hour_combo.currentData():02d}:{self.minute_combo.currentData():02d}"
        return {
            "title": self.title_edit.toPlainText().strip(),
            "notes": normalize_note_text(self.notes_edit.toPlainText()).strip(),
            "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_time": due_time,
            "is_fixed": self.fixed_check.isChecked(),
            "windows_reminder_enabled": bool(due_time) and self.windows_reminder_check.isChecked(),
            "steps": self.steps_editor.values(),
            "content_mode": "notes",
        }

    def _sync_windows_reminder_availability(self, enabled: bool) -> None:
        """Keep the important-reminder choice visible and explain its prerequisite."""
        self.windows_reminder_check.setEnabled(enabled)
        self.windows_reminder_label.setEnabled(enabled)
        if not enabled:
            self.windows_reminder_check.setChecked(False)

    def duplicate_requested(self) -> bool:
        return not self.duplicate_check.isHidden() and self.duplicate_check.isChecked()

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
