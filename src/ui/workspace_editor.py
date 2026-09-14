"""Right-hand, save-first editor used by the full-screen workspace."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_HOURS, TIME_MINUTES, normalize_note_text
from ui.task_dialog import PlainNotesEditor, TitleEditor
from ui.task_steps import TaskStepsEditor


class WorkspaceEditor(QWidget):
    """An editor that never writes until its explicit Save button is used."""

    save_requested = pyqtSignal(int, dict)
    duplicate_requested = pyqtSignal(int)
    move_today_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._task_id: int | None = None
        self._baseline: dict | None = None
        self._loading = False
        self._content_mode = "notes"
        self._task_is_previous = False

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(16, 16, 16, 16)
        self._outer_layout.setSpacing(10)
        self.heading = QLabel("选择一条事项")
        self.heading.setStyleSheet("font-size:18px; font-weight:600; color:#2c3a4d;")
        self._outer_layout.addWidget(self.heading)
        self.hint = QLabel("从中间列表选择后可直接修改；只有点击保存才会生效。")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("font-size:12px; color:#7b8795;")
        self._outer_layout.addWidget(self.hint)

        self.form_host = QWidget()
        form = QVBoxLayout(self.form_host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)

        self.title_edit = TitleEditor()
        self.title_edit.setFixedHeight(76)
        self.title_edit.setPlaceholderText("事项标题（最多两行）")
        self.title_edit.setToolTip("事项标题最多两行；Enter 转到具体内容；Shift + Enter 可换行。")
        self.title_edit.next_field_requested.connect(self._focus_content)

        self.notes_edit = PlainNotesEditor()
        self.notes_edit.setPlaceholderText("具体事项、材料或下一步")
        self.notes_edit.setMinimumHeight(380)
        self.notes_edit.setAcceptRichText(False)
        self.steps_editor = TaskStepsEditor()
        self.content_mode_button = QPushButton()
        self.content_mode_button.setObjectName("contentModeToggle")
        self.content_mode_button.setToolTip("普通文本和分项步骤是两种不同的具体内容写法。")
        self.content_mode_button.clicked.connect(self._toggle_content_mode)
        self.content_mode_button.setStyleSheet(
            "QPushButton#contentModeToggle { text-align:left; color:#587298; background:#f7faff; "
            "border:1px dashed #abc0df; border-radius:8px; padding:6px 9px; font-weight:600; }"
            "QPushButton#contentModeToggle:hover { background:#eef5ff; border-color:#7399d4; }"
        )

        self.date_edit = CompactDatePicker(QDate.currentDate())
        self.time_enabled = QCheckBox("有具体时间")
        self.hour_combo = NoWheelComboBox()
        self.minute_combo = NoWheelComboBox()
        for hour in TIME_HOURS:
            self.hour_combo.addItem(f"{hour:02d} 时", hour)
        for minute in TIME_MINUTES:
            self.minute_combo.addItem(f"{minute:02d} 分", minute)
        next_hour = min(22, max(7, QTime.currentTime().hour() + 1))
        self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(next_hour)))
        self.hour_combo.activated.connect(lambda _: self.time_enabled.setChecked(True))
        self.minute_combo.activated.connect(lambda _: self.time_enabled.setChecked(True))
        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(7)
        time_row.addWidget(self.time_enabled)
        time_row.addWidget(self.hour_combo)
        time_row.addWidget(self.minute_combo)
        time_row.addStretch()

        self.windows_reminder_check = QCheckBox("重要事项：准点强提醒（需手动关闭）")
        self.windows_reminder_check.setObjectName("windowsReminderCheck")
        self.windows_reminder_check.setToolTip("先勾选“有具体时间”后可启用。软件会弹出置顶提醒，Windows 通知可用时会作为额外提醒。")
        self.windows_reminder_check.setStyleSheet(
            "QCheckBox#windowsReminderCheck { color:#2458bf; font-weight:600; padding:5px 7px 5px 0; "
            "border:1px solid #b9ccff; border-radius:8px; background:#eef4ff; }"
        )
        self.time_enabled.toggled.connect(self._sync_windows_reminder_availability)
        self.fixed_check = QCheckBox("固定锁住待办（显示在当天列表最底部）")

        form.addWidget(self.title_edit)
        form.addWidget(self.content_mode_button)
        form.addWidget(self.notes_edit, 1)
        form.addWidget(self.steps_editor, 1)
        settings_label = QLabel("时间与提醒")
        settings_label.setStyleSheet("font-size:12px; color:#718096; font-weight:600; padding:14px 0 5px;")
        form.addWidget(settings_label)
        form.addWidget(self.date_edit)
        form.addLayout(time_row)
        form.addWidget(self.fixed_check)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color:#dbe4ee; margin:11px 0 7px;")
        form.addWidget(divider)
        # This important, optional reminder is deliberately last: it starts on
        # the same left axis as the time controls, but is visually separated
        # from ordinary scheduling choices.
        form.addWidget(self.windows_reminder_check)
        operation_divider = QFrame()
        operation_divider.setFrameShape(QFrame.Shape.HLine)
        operation_divider.setStyleSheet("color:#dbe4ee; margin:13px 0 7px;")
        form.addWidget(operation_divider)
        operations_label = QLabel("事项操作")
        operations_label.setStyleSheet("font-size:12px; color:#718096; font-weight:600; padding:0 0 5px;")
        form.addWidget(operations_label)
        self.duplicate_button = QPushButton("复制为新事项")
        self.duplicate_button.setObjectName("quietButton")
        self.duplicate_button.setToolTip("保留原事项，并新建一条可单独修改的副本。")
        self.duplicate_button.clicked.connect(self._emit_duplicate)
        self.duplicate_hint = QLabel("保留原事项；副本的分项步骤会从未完成开始。")
        self.duplicate_hint.setWordWrap(True)
        self.duplicate_hint.setStyleSheet("font-size:11px; color:#8793a2; padding:2px 3px 5px;")
        self.move_today_button = QPushButton("移到今天")
        self.move_today_button.setObjectName("quietButton")
        self.move_today_button.setToolTip("直接把原事项改期到今天，不会新建副本。")
        self.move_today_button.clicked.connect(self._emit_move_today)
        self.move_today_hint = QLabel("直接改原事项日期；若要保留旧事项，请使用“复制为新事项”。")
        self.move_today_hint.setWordWrap(True)
        self.move_today_hint.setStyleSheet("font-size:11px; color:#8793a2; padding:2px 3px 4px;")
        form.addWidget(self.duplicate_button)
        form.addWidget(self.duplicate_hint)
        form.addWidget(self.move_today_button)
        form.addWidget(self.move_today_hint)
        self._outer_layout.addWidget(self.form_host, 1)

        self.action_bar = QWidget()
        buttons = QHBoxLayout(self.action_bar)
        buttons.setContentsMargins(16, 10, 16, 10)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size:12px; color:#6f7d8d; font-weight:500;")
        buttons.addWidget(self.status_label)
        buttons.addStretch()
        self.restore_button = QPushButton("撤销本次修改")
        self.save_button = QPushButton("保存修改")
        self.restore_button.clicked.connect(self.restore_baseline)
        self.save_button.clicked.connect(self._emit_save)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.save_button)
        self._outer_layout.addWidget(self.action_bar)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._emit_save)
        self.title_edit.textChanged.connect(self._refresh_status)
        self.notes_edit.textChanged.connect(self._refresh_status)
        self.steps_editor.changed.connect(self._refresh_status)
        self.date_edit.dateChanged.connect(self._refresh_status)
        self.time_enabled.toggled.connect(self._refresh_status)
        self.hour_combo.currentIndexChanged.connect(self._refresh_status)
        self.minute_combo.currentIndexChanged.connect(self._refresh_status)
        self.windows_reminder_check.toggled.connect(self._refresh_status)
        self.fixed_check.toggled.connect(self._refresh_status)
        self._refresh_content_mode()
        self.clear()

    def _sync_windows_reminder_availability(self, enabled: bool) -> None:
        self.windows_reminder_check.setEnabled(enabled)
        if not enabled:
            self.windows_reminder_check.setChecked(False)

    def detach_action_bar(self) -> QWidget:
        """Move Save controls outside the editor scroll area and keep them visible."""
        self._outer_layout.removeWidget(self.action_bar)
        self.action_bar.setParent(None)
        return self.action_bar

    def set_status_message(self, text: str, *, changed: bool = False) -> None:
        color = "#a56e11" if changed else "#6f7d8d"
        self.status_label.setStyleSheet(f"font-size:12px; color:{color}; font-weight:500;")
        self.status_label.setText(text)

    def _refresh_status(self, *_unused) -> None:
        if self._loading:
            return
        if self._task_id is None:
            self.set_status_message("选择一条事项后可编辑")
        elif self.is_dirty():
            self.set_status_message("有未保存修改", changed=True)
        else:
            self.set_status_message("已保存")
        can_copy = self._task_id is not None and not self.is_dirty()
        self.duplicate_button.setEnabled(can_copy)
        self.duplicate_hint.setText(
            "保留原事项；副本的分项步骤会从未完成开始。"
            if can_copy else "请先保存当前修改后再复制，避免复制到未保存的内容。"
        )

    def _focus_content(self) -> None:
        (self.steps_editor if self._content_mode == "steps" else self.notes_edit).setFocus()

    def _toggle_content_mode(self) -> None:
        self._content_mode = "steps" if self._content_mode == "notes" else "notes"
        if self._content_mode == "steps" and not self.steps_editor.values():
            # A clear import path lets a user turn a pre-existing multi-line
            # description into actionable steps without losing the source text.
            imported = [line.strip() for line in self.notes_edit.toPlainText().splitlines() if line.strip()]
            if imported:
                self.steps_editor.set_steps([{"content": line, "is_completed": False} for line in imported])
        self._refresh_content_mode()
        self._refresh_status()

    def _refresh_content_mode(self) -> None:
        steps_mode = self._content_mode == "steps"
        self.notes_edit.setVisible(not steps_mode)
        self.steps_editor.setVisible(steps_mode)
        self.content_mode_button.setText(
            "← 改用普通文本" if steps_mode else "＋ 改用分项步骤"
        )
        self.content_mode_button.setToolTip(
            "分项步骤会作为这条事项的具体内容；切换回来不会删除已写的文字。"
            if steps_mode else "将具体内容改成可逐项勾选的分项步骤。已有多行文字会按行导入步骤。"
        )

    def _emit_duplicate(self) -> None:
        if self._task_id is not None and not self.is_dirty():
            self.duplicate_requested.emit(self._task_id)

    def _emit_move_today(self) -> None:
        if self._task_id is not None and self._task_is_previous:
            self.move_today_requested.emit(self._task_id)

    def clear(self) -> None:
        self._loading = True
        self._task_id = None
        self._baseline = None
        self._content_mode = "notes"
        self._task_is_previous = False
        self.heading.setText("选择一条事项")
        self.hint.setText("从中间列表选择后可直接修改；只有点击保存才会生效。")
        self.title_edit.clear()
        self.notes_edit.clear()
        self.time_enabled.setChecked(False)
        self.windows_reminder_check.setChecked(False)
        self._sync_windows_reminder_availability(False)
        self.fixed_check.setChecked(False)
        self.steps_editor.set_steps([])
        self._loading = False
        self.form_host.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.duplicate_button.setEnabled(False)
        self.move_today_button.setVisible(False)
        self.move_today_hint.setVisible(False)
        self._refresh_content_mode()
        self.set_status_message("选择一条事项后可编辑")

    def load_task(self, task, task_steps=None) -> None:
        if task is None:
            self.clear()
            return
        self._loading = True
        self._task_id = int(task["id"])
        self._task_is_previous = not bool(task["is_completed"]) and task["task_date"] < QDate.currentDate().toString("yyyy-MM-dd")
        self.heading.setText("编辑事项")
        self.hint.setText("可以安心复制或调整内容；点击保存后才会写入这条事项。")
        self.title_edit.setPlainText(task["title"])
        self.notes_edit.setPlainText(normalize_note_text(task["notes"]))
        self.steps_editor.set_steps(task_steps)
        self._content_mode = (
            task["content_mode"] if "content_mode" in task.keys() and task["content_mode"] == "steps"
            else "notes"
        )
        self.date_edit.setDate(QDate.fromString(task["task_date"], "yyyy-MM-dd"))
        due = task["due_time"]
        self.time_enabled.setChecked(bool(due))
        if due:
            hour, minute = due.split(":", 1)
            self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(int(hour))))
            index = self.minute_combo.findData(int(minute))
            if index < 0:
                self.minute_combo.addItem(f"{int(minute):02d} 分（原时间）", int(minute))
                index = self.minute_combo.count() - 1
            self.minute_combo.setCurrentIndex(index)
        supports_reminder = "windows_reminder_enabled" in task.keys()
        self.windows_reminder_check.setChecked(bool(supports_reminder and task["windows_reminder_enabled"]))
        self._sync_windows_reminder_availability(bool(due))
        self.fixed_check.setChecked(bool(task["is_fixed"]))
        self._loading = False
        self._refresh_content_mode()
        self.form_host.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.move_today_button.setVisible(self._task_is_previous)
        self.move_today_hint.setVisible(self._task_is_previous)
        self._baseline = self.values()
        self._refresh_status()

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
            "content_mode": self._content_mode,
        }

    def is_dirty(self) -> bool:
        return self._task_id is not None and self._baseline != self.values()

    def restore_baseline(self) -> None:
        if self._task_id is None or self._baseline is None:
            return
        values = self._baseline
        self._loading = True
        self.title_edit.setPlainText(values["title"])
        self.notes_edit.setPlainText(values["notes"])
        self._content_mode = values.get("content_mode", "notes")
        self.date_edit.setDate(QDate.fromString(values["task_date"], "yyyy-MM-dd"))
        self.time_enabled.setChecked(bool(values["due_time"]))
        if values["due_time"]:
            hour, minute = values["due_time"].split(":", 1)
            self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(int(hour))))
            self.minute_combo.setCurrentIndex(max(0, self.minute_combo.findData(int(minute))))
        self.windows_reminder_check.setChecked(values["windows_reminder_enabled"])
        self._sync_windows_reminder_availability(bool(values["due_time"]))
        self.fixed_check.setChecked(values["is_fixed"])
        self.steps_editor.set_steps(values.get("steps", []))
        self._loading = False
        self._refresh_content_mode()
        self._refresh_status()

    def _emit_save(self) -> None:
        if self._task_id is None:
            return
        values = self.values()
        if not values["title"]:
            self.title_edit.setFocus()
            return
        self.set_status_message("正在保存…")
        self.save_requested.emit(self._task_id, values)

    def mark_saved(self, task, task_steps=None) -> None:
        """Reload the authoritative saved row as the next clean baseline."""
        self.load_task(task, task_steps)
