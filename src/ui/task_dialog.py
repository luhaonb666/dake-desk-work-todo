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
    QWidget,
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
        self._duplicate_requested = False
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
        self.steps_editor.next_field_requested.connect(self.notes_edit.setFocus)
        self.notes_section = QFrame()
        notes_layout = QVBoxLayout(self.notes_section)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(0)
        notes_content = QHBoxLayout()
        notes_content.setContentsMargins(0, 0, 0, 0)
        notes_content.setSpacing(7)
        notes_content.addWidget(self.notes_edit, 1)
        self.import_steps_rail = QFrame()
        self.import_steps_rail.setObjectName("importStepsRail")
        # This rail is a conversion affordance, not a second editor. Keep it
        # only as wide as its two-line action label plus a little breathing room.
        self.import_steps_rail.setFixedWidth(72)
        self.import_steps_rail.setFixedHeight(self.notes_edit.height())
        self.import_steps_rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.import_steps_rail.setStyleSheet(
            "QFrame#importStepsRail { background:#f7faff; border:1px solid #c8d7ef; border-radius:9px; }"
        )
        rail_layout = QVBoxLayout(self.import_steps_rail)
        rail_layout.setContentsMargins(4, 6, 4, 6)
        rail_layout.setSpacing(4)
        self.import_steps_button = QPushButton("⇩\n拆成步骤")
        self.import_steps_button.setObjectName("importStepsButton")
        self.import_steps_button.setToolTip("把正文中每个非空行各新增为一个待办步骤；原正文不会删除。")
        self.import_steps_button.setStyleSheet(
            "QPushButton#importStepsButton { color:#426ca8; background:#ffffff; border:1px solid #aebfe0; "
            "border-radius:7px; padding:5px 2px; font-size:12px; font-weight:600; }"
            "QPushButton#importStepsButton:hover { background:#eef4ff; border-color:#7597d1; }"
            "QPushButton#importStepsButton:disabled { color:#9ca9b9; background:#f7f9fc; border-color:#dce4ef; }"
        )
        self.import_steps_hint = QLabel("按每行\n新增一步\n\n正文保留")
        self.import_steps_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.import_steps_hint.setToolTip("把正文的每个非空行复制成一条待办步骤，原正文不会删除。")
        self.import_steps_hint.setStyleSheet("font-size:10px; color:#7f8da0; line-height:1.35;")
        rail_layout.addWidget(self.import_steps_button)
        rail_layout.addWidget(self.import_steps_hint)
        rail_layout.addStretch(1)
        notes_content.addWidget(self.import_steps_rail, 0)
        notes_layout.addLayout(notes_content)
        self.import_steps_button.clicked.connect(self._import_note_lines)
        self.notes_edit.textChanged.connect(self._refresh_import_button)
        self.steps_editor.structure_changed.connect(self._refresh_step_layout)

        self.date_edit = CompactDatePicker()
        selected = QDate.fromString(task["task_date"], "yyyy-MM-dd") if task else QDate.currentDate()
        self.date_edit.setDate(selected)

        self.time_enabled = QCheckBox("有具体时间")
        self.time_enabled.setChecked(bool(task and task["due_time"]))
        task_supports_system_reminder = bool(task and "windows_reminder_enabled" in task.keys())
        reminder_enabled = bool(task and task_supports_system_reminder and task["windows_reminder_enabled"])
        reminder_offset = int(task["important_reminder_offset_minutes"]) if task and "important_reminder_offset_minutes" in task.keys() else 0
        reminder_repeat_minutes = int(task["important_repeat_minutes"]) if task and "important_repeat_minutes" in task.keys() else 0
        reminder_repeat_limit = int(task["important_repeat_limit"]) if task and "important_repeat_limit" in task.keys() else 0
        self.important_reminder_check = QCheckBox("启用重要提醒")
        self.important_reminder_check.setChecked(reminder_enabled)
        self.important_reminder_check.setToolTip("勾选后，软件会在右下角显示置顶提醒；提醒可关闭或稍后提醒。")
        self.reminder_timing_combo = NoWheelComboBox()
        for label, minutes in (
            ("事项时间：准点提醒", 0),
            ("事项时间前 10 分钟", 10),
            ("事项时间前 30 分钟", 30),
            ("事项时间前 1 小时", 60),
            ("事项时间前 1 天", 24 * 60),
            ("事项时间前 3 天", 3 * 24 * 60),
        ):
            self.reminder_timing_combo.addItem(label, minutes)
        self.reminder_timing_combo.setCurrentIndex(max(0, self.reminder_timing_combo.findData(reminder_offset)))
        self.reminder_timing_combo.setToolTip("选择何时显示软件内强提醒；事项本身的日期和时间不会改变。")
        self.windows_reminder_box = QFrame()
        self.windows_reminder_box.setObjectName("windowsReminderBox")
        self.windows_reminder_box.setStyleSheet(
            "QFrame#windowsReminderBox { border:1px solid #d5e0ef; border-radius:8px; background:#fafcff; }"
        )
        reminder_layout = QVBoxLayout(self.windows_reminder_box)
        reminder_layout.setContentsMargins(10, 7, 10, 7)
        reminder_layout.setSpacing(5)
        reminder_layout.addWidget(self.important_reminder_check)
        self.reminder_summary = QLabel("软件会在右下角置顶提醒；关闭提醒不会完成事项。")
        self.reminder_summary.setWordWrap(True)
        self.reminder_summary.setStyleSheet("font-size:11px; color:#718096; background:transparent; padding-left:23px;")
        reminder_layout.addWidget(self.reminder_summary)
        self.reminder_expand_button = QPushButton("展开提醒设置")
        self.reminder_expand_button.setCheckable(True)
        self.reminder_expand_button.setChecked(reminder_enabled)
        self.reminder_expand_button.setStyleSheet(
            "QPushButton { text-align:left; color:#466fa5; background:transparent; border:none; padding:2px 0 2px 23px; font-size:11px; }"
            "QPushButton:hover { color:#254f8a; }"
        )
        reminder_layout.addWidget(self.reminder_expand_button)
        self.reminder_details = QWidget()
        details_layout = QVBoxLayout(self.reminder_details)
        details_layout.setContentsMargins(23, 2, 0, 1)
        details_layout.setSpacing(4)
        reminder_time_row = QHBoxLayout()
        reminder_time_row.setContentsMargins(0, 0, 0, 0)
        reminder_time_row.addWidget(QLabel("提醒时间"))
        reminder_time_row.addWidget(self.reminder_timing_combo, 1)
        details_layout.addLayout(reminder_time_row)
        self.reminder_repeat_check = QCheckBox("关闭后继续提醒")
        self.reminder_repeat_check.setChecked(reminder_repeat_minutes > 0 and reminder_repeat_limit > 0)
        self.reminder_repeat_check.setToolTip("每次关闭提醒后，按设定间隔再次显示，直到达到次数上限。")
        details_layout.addWidget(self.reminder_repeat_check)
        self.reminder_repeat_row = QWidget()
        repeat_row = QHBoxLayout(self.reminder_repeat_row)
        repeat_row.setContentsMargins(23, 0, 0, 0)
        repeat_row.setSpacing(5)
        repeat_row.addWidget(QLabel("间隔"))
        self.reminder_repeat_interval_combo = NoWheelComboBox()
        for label, minutes in (("10 分钟", 10), ("30 分钟", 30), ("1 小时", 60), ("2 小时", 120)):
            self.reminder_repeat_interval_combo.addItem(label, minutes)
        self.reminder_repeat_interval_combo.setCurrentIndex(
            max(0, self.reminder_repeat_interval_combo.findData(reminder_repeat_minutes or 30))
        )
        repeat_row.addWidget(self.reminder_repeat_interval_combo)
        repeat_row.addWidget(QLabel("重复"))
        self.reminder_repeat_limit_combo = NoWheelComboBox()
        for label, count in (("1 次", 1), ("2 次", 2), ("3 次", 3), ("5 次", 5)):
            self.reminder_repeat_limit_combo.addItem(label, count)
        self.reminder_repeat_limit_combo.setCurrentIndex(
            max(0, self.reminder_repeat_limit_combo.findData(reminder_repeat_limit or 2))
        )
        repeat_row.addWidget(self.reminder_repeat_limit_combo)
        repeat_row.addStretch()
        details_layout.addWidget(self.reminder_repeat_row)
        repeat_hint = QLabel("“稍后提醒”始终从你点击的此刻开始计算；此处只设置关闭提醒后的自动再次提醒。")
        repeat_hint.setWordWrap(True)
        repeat_hint.setStyleSheet("font-size:10px; color:#8793a2; background:transparent;")
        details_layout.addWidget(repeat_hint)
        reminder_layout.addWidget(self.reminder_details)
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
        self.important_reminder_check.toggled.connect(self._sync_windows_reminder_availability)
        self.important_reminder_check.toggled.connect(self._refresh_reminder_details)
        self.reminder_expand_button.toggled.connect(self._refresh_reminder_details)
        self.reminder_repeat_check.toggled.connect(self._refresh_reminder_details)

        self.fixed_check = QCheckBox("固定锁住待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        form.addRow("事项标题", title_box)
        form.addRow("", self.steps_editor)
        form.addRow("具体内容", self.notes_section)
        form.addRow("日期", self.date_edit)
        form.addRow("时间", time_box)
        form.addRow("", self.fixed_check)
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
        self.follow_up_button = QPushButton("新建为后续事项")
        self.follow_up_button.setObjectName("quietButton")
        self.follow_up_button.setToolTip("保留当前事项，并按当前内容新建一条可继续处理的后续事项。")
        self.follow_up_button.setVisible(bool(task))
        self.follow_up_button.clicked.connect(self._accept_as_follow_up)
        buttons.addButton(self.follow_up_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.accept)
        self._refresh_import_button()

    def _import_note_lines(self) -> None:
        text = self.notes_edit.toPlainText()
        imported = self.steps_editor.import_note_lines(text)
        if imported:
            self._refresh_import_button()

    def _refresh_import_button(self) -> None:
        text = self.notes_edit.toPlainText()
        has_lines = bool([line for line in text.splitlines() if line.strip()])
        self.import_steps_button.setEnabled(has_lines)
        # Conversion stays available after every use: users often continue
        # editing the body and need to split its current lines again.
        self.import_steps_button.setText("⇩\n拆成步骤")

    def _refresh_step_layout(self) -> None:
        """Let the form reclaim removed-row space without resizing the dialog."""
        self.steps_editor.updateGeometry()
        self.notes_section.updateGeometry()
        self.layout().activate()

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
            "windows_reminder_enabled": bool(due_time) and self.important_reminder_check.isChecked(),
            "important_reminder_offset_minutes": (
                int(self.reminder_timing_combo.currentData())
                if due_time and self.important_reminder_check.isChecked() else 0
            ),
            "important_repeat_minutes": (
                int(self.reminder_repeat_interval_combo.currentData())
                if due_time and self.important_reminder_check.isChecked() and self.reminder_repeat_check.isChecked() else 0
            ),
            "important_repeat_limit": (
                int(self.reminder_repeat_limit_combo.currentData())
                if due_time and self.important_reminder_check.isChecked() and self.reminder_repeat_check.isChecked() else 0
            ),
            "steps": self.steps_editor.values(),
            "content_mode": "notes",
        }

    def _sync_windows_reminder_availability(self, enabled: bool) -> None:
        """Keep reminder choices tied to a real task date and time."""
        self.important_reminder_check.setEnabled(enabled)
        if not enabled:
            self.important_reminder_check.setChecked(False)
        active = enabled and self.important_reminder_check.isChecked()
        self.reminder_expand_button.setEnabled(active)
        self.reminder_timing_combo.setEnabled(active)
        self.reminder_repeat_check.setEnabled(active)
        self.reminder_repeat_interval_combo.setEnabled(active and self.reminder_repeat_check.isChecked())
        self.reminder_repeat_limit_combo.setEnabled(active and self.reminder_repeat_check.isChecked())
        self._refresh_reminder_details()

    def _refresh_reminder_details(self, *_unused) -> None:
        active = self.time_enabled.isChecked() and self.important_reminder_check.isChecked()
        expanded = active and self.reminder_expand_button.isChecked()
        self.reminder_details.setVisible(expanded)
        self.reminder_repeat_row.setVisible(expanded and self.reminder_repeat_check.isChecked())
        self.reminder_expand_button.setText("收起提醒设置" if expanded else "展开提醒设置")

    def duplicate_requested(self) -> bool:
        return self._duplicate_requested

    def _accept_as_follow_up(self) -> None:
        """Confirm the non-destructive path before turning Save into a copy."""
        if not self.title_edit.toPlainText().strip():
            self.title_edit.setFocus()
            return
        answer = QMessageBox.question(
            self,
            "新建为后续事项",
            "将保留当前事项，并新建一条相同内容的后续事项。\n新事项可单独继续修改，分项步骤会从未完成开始。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._duplicate_requested = True
        self._accept_current_values()

    def accept(self) -> None:
        self._duplicate_requested = False
        self._accept_current_values()

    def _accept_current_values(self) -> None:
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
