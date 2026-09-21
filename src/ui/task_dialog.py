"""Task editor with deliberate keyboard behaviour and flexible time selection."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QButtonGroup,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_COMBO_WIDTH, TIME_HOURS, TIME_MINUTES, normalize_note_text
from ui.important_schedule import ImportantReminderEditorDialog, ImportantReminderSchedule
from ui.task_steps import CompactStepStartButton, TaskStepsEditor
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
        # A new item is constructed without a task object.  Existing task
        # dictionaries from older call sites may not carry an id yet.
        self._is_existing_task = bool(task)
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
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
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
        self.steps_editor.use_external_start_button()
        self.steps_editor.next_field_requested.connect(self.notes_edit.setFocus)
        self.notes_section = QFrame()
        notes_layout = QVBoxLayout(self.notes_section)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(0)
        notes_header = QHBoxLayout()
        notes_header.setContentsMargins(0, 0, 0, 2)
        notes_header.addStretch(1)
        self.add_step_button = CompactStepStartButton()
        self.add_step_button.setMinimumWidth(210)
        self.add_step_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.add_step_button.clicked.connect(self.steps_editor.start)
        notes_header.addWidget(self.add_step_button, 2)
        notes_layout.addLayout(notes_header)
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
        reminder_at = task["important_reminder_at"] if task and "important_reminder_at" in task.keys() else None
        self._legacy_reminder_at = str(reminder_at) if reminder_at else None
        self._schedule_touched = False
        self._event_type = task["event_type"] if task and "event_type" in task.keys() else "todo"
        self.important_reminder_check = QCheckBox("启用重要提醒")
        self.important_reminder_check.setChecked(reminder_enabled)
        self.important_reminder_check.setToolTip("勾选后，软件会在右下角显示置顶提醒；提醒可关闭或稍后提醒。")
        self._reminder_choice = f"offset:{reminder_offset}" if reminder_offset in (0, 10, 30) else "custom"
        self.windows_reminder_box = QFrame()
        self.windows_reminder_box.setObjectName("windowsReminderBox")
        self.windows_reminder_box.setStyleSheet(
            "QFrame#windowsReminderBox { border:1px solid #d5e0ef; border-radius:8px; background:#fafcff; }"
        )
        reminder_layout = QVBoxLayout(self.windows_reminder_box)
        reminder_layout.setContentsMargins(10, 7, 10, 7)
        reminder_layout.setSpacing(5)
        reminder_content = QWidget()
        reminder_content_row = QHBoxLayout(reminder_content)
        reminder_content_row.setContentsMargins(0, 0, 0, 0)
        reminder_content_row.setSpacing(12)
        reminder_left = QWidget()
        self._reminder_left_layout = QVBoxLayout(reminder_left)
        self._reminder_left_layout.setContentsMargins(0, 0, 0, 0)
        self._reminder_left_layout.setSpacing(5)
        reminder_content_row.addWidget(reminder_left, 1)
        reminder_layout.addWidget(reminder_content)
        reminder_header = QHBoxLayout()
        reminder_header.setContentsMargins(0, 0, 0, 0)
        reminder_header.addWidget(self.important_reminder_check)
        self.open_important_editor_button = QPushButton("设置重要提醒")
        self.open_important_editor_button.setObjectName("importantReminderEditorButton")
        self.open_important_editor_button.setToolTip("在独立页面设置提醒时间与重复方式，不会改动待办日期或时间。")
        self.open_important_editor_button.clicked.connect(self._edit_important_reminder)
        self.open_important_editor_button.setStyleSheet(
            "QPushButton#importantReminderEditorButton { min-width:190px; padding:10px 16px; color:#426b9f; "
            "background:#fff; border:1px solid #9db9df; border-radius:8px; font-weight:600; }"
            "QPushButton#importantReminderEditorButton:hover { background:#edf4ff; border-color:#6f95cf; }"
        )
        self.open_important_editor_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        reminder_content_row.addWidget(self.open_important_editor_button, 0)
        self._reminder_left_layout.addLayout(reminder_header)
        self.reminder_summary = QLabel("软件会在右下角置顶提醒；关闭提醒不会完成事项。")
        self.reminder_summary.setWordWrap(True)
        self.reminder_summary.setStyleSheet("font-size:11px; color:#718096; background:transparent; padding-left:23px;")
        self._reminder_left_layout.addWidget(self.reminder_summary)
        self.reminder_details = QWidget()
        details_layout = QVBoxLayout(self.reminder_details)
        details_layout.setContentsMargins(23, 2, 0, 1)
        details_layout.setSpacing(4)
        self.reminder_basis_host = QWidget()
        basis_row = QHBoxLayout(self.reminder_basis_host)
        basis_row.setContentsMargins(0, 0, 0, 0)
        basis_row.addWidget(QLabel("提醒基准"))
        self.reminder_basis_group = QButtonGroup(self)
        self.reminder_basis_buttons: dict[str, QPushButton] = {}
        for key, label in (("task_time", "按事项时间"), ("from_now", "从现在起")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
                "QPushButton:disabled, QPushButton:checked:disabled { color:#98a3b2; background:#f2f4f7; border-color:#d8e0ea; }"
            )
            self.reminder_basis_group.addButton(button)
            self.reminder_basis_buttons[key] = button
            button.clicked.connect(lambda _checked=False, value=key: self._choose_reminder_basis(value))
            basis_row.addWidget(button)
        basis_row.addStretch()
        details_layout.addWidget(self.reminder_basis_host)
        self.task_time_choices = QWidget()
        choice_row = QHBoxLayout(self.task_time_choices)
        choice_row.setContentsMargins(0, 0, 0, 0)
        choice_row.setSpacing(5)
        self.reminder_choice_group = QButtonGroup(self)
        self.reminder_choice_group.setExclusive(False)
        self.reminder_choice_buttons: dict[str, QPushButton] = {}
        for key, label in (("offset:0", "准点"), ("offset:10", "提前 10 分"), ("offset:30", "提前半小时")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
            )
            self.reminder_choice_group.addButton(button)
            self.reminder_choice_buttons[key] = button
            button.clicked.connect(lambda _checked=False, value=key: self._choose_reminder(value))
            choice_row.addWidget(button)
        self.custom_offset_combo = NoWheelComboBox()
        self.custom_offset_combo.setObjectName("reminderOffsetCombo")
        self.custom_offset_combo.addItem("自定义 ▾", None)
        for label, minutes in (("提前 1 小时", 60), ("提前 2 小时", 120), ("提前 3 小时", 180), ("提前 4 小时", 240)):
            self.custom_offset_combo.addItem(label, minutes)
        self.custom_offset_combo.setStyleSheet(
            "QComboBox#reminderOffsetCombo { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
            "QComboBox#reminderOffsetCombo:hover { background:#f3f7ff; border-color:#7597d1; }"
        )
        self.custom_offset_combo.currentIndexChanged.connect(self._choose_custom_offset)
        if self._reminder_choice == "custom":
            self.custom_offset_combo.setCurrentIndex(max(1, self.custom_offset_combo.findData(reminder_offset)))
        choice_row.addWidget(self.custom_offset_combo)
        choice_row.addStretch()
        details_layout.addWidget(self.task_time_choices)
        self._reminder_left_layout.addWidget(self.reminder_details)
        self.switch_to_reminder_button = QPushButton("设为提醒事件")
        self.switch_to_reminder_button.setObjectName("quietButton")
        self.switch_to_reminder_button.setToolTip("提醒事件可设置快捷提醒时间与重复规则；已有内容和分项步骤会保留。")
        self.switch_to_reminder_button.clicked.connect(lambda: self._set_event_type("reminder"))
        self._reminder_left_layout.addWidget(self.switch_to_reminder_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.important_schedule = ImportantReminderSchedule()
        self.important_schedule.load(task) if task else self.important_schedule.set_task_date(self.date_edit.date())
        self.important_schedule.changed.connect(self._mark_schedule_touched)
        self._reminder_left_layout.addWidget(self.important_schedule)
        self.quick_reminder_host = QWidget()
        quick_reminder_row = QHBoxLayout(self.quick_reminder_host)
        quick_reminder_row.setContentsMargins(23, 1, 0, 1)
        quick_reminder_row.setSpacing(5)
        quick_reminder_row.addWidget(QLabel("简单提醒"))
        self.quick_reminder_buttons: dict[int, QPushButton] = {}
        self.quick_reminder_group = QButtonGroup(self)
        for minutes, label in ((0, "准点"), (10, "提前 10 分"), (30, "提前半小时")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
                "QPushButton:disabled, QPushButton:checked:disabled { color:#98a3b2; background:#f2f4f7; border-color:#d8e0ea; }"
            )
            button.clicked.connect(lambda _checked=False, value=minutes: self._set_quick_reminder_offset(value))
            self.quick_reminder_group.addButton(button)
            self.quick_reminder_buttons[minutes] = button
            quick_reminder_row.addWidget(button)
        self.quick_reminder_custom = NoWheelComboBox()
        self.quick_reminder_custom.addItem("自定义 ▾", None)
        for hours in range(1, 5):
            self.quick_reminder_custom.addItem(f"提前 {hours} 小时", hours * 60)
        self.quick_reminder_custom.setStyleSheet(
            "QComboBox { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
            "QComboBox:disabled { color:#98a3b2; background:#f2f4f7; border-color:#d8e0ea; }"
        )
        self.quick_reminder_custom.currentIndexChanged.connect(self._set_quick_custom_reminder)
        quick_reminder_row.addWidget(self.quick_reminder_custom)
        quick_reminder_row.addStretch()
        self._reminder_left_layout.addWidget(self.quick_reminder_host)
        self.quick_reminder_notice = QLabel()
        self.quick_reminder_notice.setWordWrap(True)
        self.quick_reminder_notice.setStyleSheet("font-size:11px; color:#718096; padding-left:23px;")
        self._reminder_left_layout.addWidget(self.quick_reminder_notice)
        self.important_schedule.changed.connect(self._refresh_quick_reminder_controls)
        self.recurrence_box = QFrame()
        self.recurrence_box.setObjectName("recurrenceBox")
        self.recurrence_box.setStyleSheet(
            "QFrame#recurrenceBox { border:1px solid #dce5ef; border-radius:8px; background:#ffffff; }"
        )
        recurrence_layout = QHBoxLayout(self.recurrence_box)
        recurrence_layout.setContentsMargins(10, 6, 10, 6)
        recurrence_layout.setSpacing(7)
        recurrence_layout.addWidget(QLabel("重复事项"))
        self.recurrence_combo = NoWheelComboBox()
        for label, unit in (("不重复", "none"), ("每天", "day"), ("工作日", "workday"), ("每周", "week"), ("每月", "month"), ("每年", "year"), ("自定义", "custom")):
            self.recurrence_combo.addItem(label, unit)
        recurrence_unit = task["recurrence_unit"] if task and "recurrence_unit" in task.keys() else "none"
        recurrence_interval = int(task["recurrence_interval"] or 1) if task and "recurrence_interval" in task.keys() else 1
        self.recurrence_combo.setCurrentIndex(max(0, self.recurrence_combo.findData(recurrence_unit)))
        recurrence_layout.addWidget(self.recurrence_combo)
        self.recurrence_custom = QWidget()
        recurrence_custom_layout = QHBoxLayout(self.recurrence_custom)
        recurrence_custom_layout.setContentsMargins(0, 0, 0, 0)
        recurrence_custom_layout.setSpacing(4)
        recurrence_custom_layout.addWidget(QLabel("每"))
        self.recurrence_interval_spin = QSpinBox()
        self.recurrence_interval_spin.setRange(1, 99)
        self.recurrence_interval_spin.setValue(recurrence_interval)
        self.recurrence_interval_spin.setFixedWidth(48)
        recurrence_custom_layout.addWidget(self.recurrence_interval_spin)
        self.recurrence_unit_combo = NoWheelComboBox()
        for label, unit in (("天", "day"), ("周", "week"), ("月", "month"), ("年", "year")):
            self.recurrence_unit_combo.addItem(label, unit)
        self.recurrence_unit_combo.setCurrentIndex(max(0, self.recurrence_unit_combo.findData(recurrence_unit if recurrence_unit != "none" else "day")))
        recurrence_custom_layout.addWidget(self.recurrence_unit_combo)
        recurrence_layout.addWidget(self.recurrence_custom)
        recurrence_layout.addStretch()
        self.hour_combo = NoWheelComboBox()
        for hour in TIME_HOURS:
            self.hour_combo.addItem(f"{hour:02d} 时", hour)
        self.minute_combo = NoWheelComboBox()
        for minute in TIME_MINUTES:
            self.minute_combo.addItem(f"{minute:02d} 分", minute)
        self.hour_combo.setFixedWidth(TIME_COMBO_WIDTH)
        self.minute_combo.setFixedWidth(TIME_COMBO_WIDTH)
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
        self.reminder_event_quick = QWidget()
        quick_row = QHBoxLayout(self.reminder_event_quick)
        quick_row.setContentsMargins(0, 0, 0, 0)
        quick_row.setSpacing(5)
        quick_row.addWidget(QLabel("提醒我"))
        for label, key in (("今天稍后", "later_today"), ("明天 09:00", "tomorrow"), ("下周一 09:00", "next_monday"), ("选择日期和时间", "pick")):
            button = QPushButton(label)
            button.setObjectName("quietButton")
            button.clicked.connect(lambda _checked=False, value=key: self._apply_reminder_quick(value))
            quick_row.addWidget(button)
        quick_row.addStretch()
        self._sync_windows_reminder_availability(self.time_enabled.isChecked())
        self.time_enabled.toggled.connect(self._sync_windows_reminder_availability)
        self.important_reminder_check.toggled.connect(self._sync_windows_reminder_availability)
        self.important_reminder_check.toggled.connect(self._refresh_reminder_details)
        self.date_edit.dateChanged.connect(self.important_schedule.set_task_date)
        self.recurrence_combo.currentIndexChanged.connect(self._refresh_recurrence_details)
        self._refresh_recurrence_details()
        self._choose_reminder(self._reminder_choice, touched=False)
        self._choose_reminder_basis("task_time")

        self.fixed_check = QCheckBox("固定锁住待办（显示在当天列表最底部）")
        self.fixed_check.setChecked(bool(task and task["is_fixed"]))
        self.event_type_box = QWidget()
        type_layout = QHBoxLayout(self.event_type_box)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(5)
        type_layout.addWidget(QLabel("事项类型"))
        self.event_type_group = QButtonGroup(self)
        self.event_type_buttons: dict[str, QPushButton] = {}
        for key, label in (("todo", "待办事项"), ("reminder", "提醒事件")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 9px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
            )
            self.event_type_group.addButton(button)
            self.event_type_buttons[key] = button
            button.clicked.connect(lambda _checked=False, value=key: self._set_event_type(value))
            type_layout.addWidget(button)
        type_layout.addStretch()
        form.setVerticalSpacing(3)
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
        # A manually taller dialog must leave its spare height below the form,
        # never stretch the title/hint row into a visually random gap.
        layout.addLayout(form, 0)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.follow_up_button = QPushButton("保留原事项，另建后续")
        self.follow_up_button.setObjectName("quietButton")
        self.follow_up_button.setToolTip("保留原事项，新建一条后续事项；分项步骤会从未完成开始。")
        self.follow_up_button.clicked.connect(self._accept_as_follow_up)
        buttons.addButton(self.follow_up_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.follow_up_button.setVisible(self._is_existing_task)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.accept)
        self._refresh_event_type()
        self._refresh_import_button()

    def _import_note_lines(self) -> None:
        text = self.notes_edit.toPlainText()
        imported = self.steps_editor.import_note_lines(text)
        if imported:
            self._refresh_import_button()

    def _refresh_import_button(self) -> None:
        text = self.notes_edit.toPlainText()
        line_count = len([line for line in text.splitlines() if line.strip()])
        can_split = line_count >= 2
        self.import_steps_rail.setVisible(can_split)
        self.import_steps_button.setEnabled(can_split)
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
        reminder_enabled = self.important_reminder_check.isChecked()
        reminder_values = self.important_schedule.values()
        return {
            "title": self.title_edit.toPlainText().strip(),
            "notes": normalize_note_text(self.notes_edit.toPlainText()).strip(),
            "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_time": due_time,
            "is_fixed": self.fixed_check.isChecked(),
            "windows_reminder_enabled": reminder_enabled,
            "important_reminder_offset_minutes": reminder_values["important_reminder_offset_minutes"] if reminder_enabled else 0,
            "important_reminder_at": reminder_values["important_reminder_at"],
            "important_reminder_mode": reminder_values["important_reminder_mode"],
            "important_reminder_start_date": reminder_values["important_reminder_start_date"],
            "important_reminder_target_date": reminder_values["important_reminder_target_date"],
            "important_reminder_time": reminder_values["important_reminder_time"],
            "important_reminder_lead_days": reminder_values["important_reminder_lead_days"],
            "important_reminder_weekday": reminder_values["important_reminder_weekday"],
            "important_reminder_repeat_unit": reminder_values["important_reminder_repeat_unit"],
            "important_reminder_repeat_interval": reminder_values["important_reminder_repeat_interval"],
            "important_reminder_drafts": reminder_values["important_reminder_drafts"],
            "recurrence_unit": (
                self.recurrence_unit_combo.currentData()
                if self.recurrence_combo.currentData() == "custom" else self.recurrence_combo.currentData()
            ),
            "recurrence_interval": self.recurrence_interval_spin.value() if self.recurrence_combo.currentData() == "custom" else 1,
            "steps": self.steps_editor.values(),
            "content_mode": "notes",
            "event_type": self._event_type,
        }

    def _sync_windows_reminder_availability(self, enabled: bool) -> None:
        self.reminder_basis_buttons["task_time"].setEnabled(enabled)
        self.important_schedule.set_task_time_available(enabled)
        self._refresh_reminder_details()

    def _refresh_reminder_details(self, *_unused) -> None:
        active = self.important_reminder_check.isChecked()
        self.reminder_details.setVisible(False)
        self.reminder_basis_host.setVisible(False)
        self.task_time_choices.setVisible(False)
        self.important_schedule.setVisible(False)
        self.quick_reminder_host.setVisible(True)
        self.open_important_editor_button.setText("重要提醒设置")
        self._refresh_quick_reminder_controls()

    def _edit_important_reminder(self) -> None:
        schedule_values = self.important_schedule.values()
        if not self.important_schedule.has_selection():
            # Keep the draft fields available, but do not turn the default
            # follow mode into an accidental active selection in the dialog.
            schedule_values.pop("important_reminder_mode", None)
        dialog = ImportantReminderEditorDialog(self.date_edit.date(), schedule_values, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.important_schedule.load({
                "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
                **dialog.values(),
            })
            self.important_reminder_check.setChecked(True)
            self._mark_schedule_touched()
            self._refresh_reminder_details()

    def _set_quick_reminder_offset(self, minutes: int) -> None:
        self.time_enabled.setChecked(True)
        self.important_reminder_check.setChecked(True)
        self.important_schedule._set_mode("follow")
        self.important_schedule._set_offset(minutes)
        self._refresh_reminder_details()

    def _set_quick_custom_reminder(self, index: int) -> None:
        minutes = self.quick_reminder_custom.itemData(index)
        if minutes:
            self._set_quick_reminder_offset(int(minutes))

    def _refresh_quick_reminder_controls(self, *_unused) -> None:
        if not hasattr(self, "quick_reminder_buttons"):
            return
        values = self.important_schedule.values()
        mode = self.important_schedule.selected_mode() or "follow"
        complex_plan = self.important_reminder_check.isChecked() and mode in {"deadline", "weekly"}
        offset = (
            values["important_reminder_offset_minutes"]
            if self.important_reminder_check.isChecked() and mode == "follow"
            else None
        )
        self.quick_reminder_group.setExclusive(False)
        for minutes, button in self.quick_reminder_buttons.items():
            button.setChecked(not complex_plan and offset == minutes)
            button.setEnabled(not complex_plan)
        self.quick_reminder_group.setExclusive(True)
        self.quick_reminder_custom.blockSignals(True)
        index = self.quick_reminder_custom.findData(offset) if not complex_plan and offset not in self.quick_reminder_buttons and offset else 0
        self.quick_reminder_custom.setCurrentIndex(index)
        self.quick_reminder_custom.blockSignals(False)
        self.quick_reminder_custom.setEnabled(not complex_plan)
        if complex_plan:
            plan_name = "目标日提醒" if mode == "deadline" else "周期提醒"
            self.quick_reminder_notice.setText(f"当前仅启用{plan_name}；简单提醒已关闭，不能叠加。请在“重要提醒设置”中修改。")
        else:
            self.quick_reminder_notice.clear()
        self.quick_reminder_notice.setVisible(complex_plan)

    def _choose_reminder(self, value: str, *, touched: bool = True) -> None:
        self._reminder_choice = value
        for key, button in self.reminder_choice_buttons.items():
            button.setChecked(key == value)
        if value != "custom":
            self.custom_offset_combo.blockSignals(True)
            self.custom_offset_combo.setCurrentIndex(0)
            self.custom_offset_combo.blockSignals(False)
        if touched:
            self._mark_schedule_touched()
        self._refresh_reminder_details()

    def _choose_reminder_basis(self, value: str) -> None:
        self.reminder_basis_buttons[value].setChecked(True)
        self._refresh_reminder_details()

    def _mark_schedule_touched(self, *_unused) -> None:
        self._schedule_touched = True
        self._legacy_reminder_at = None

    def _choose_custom_offset(self, index: int) -> None:
        if index <= 0:
            return
        self._reminder_choice = "custom"
        for button in self.reminder_choice_buttons.values():
            button.setChecked(False)
        self._mark_schedule_touched()
        self._refresh_reminder_details()

    def _set_event_type(self, value: str) -> None:
        self._event_type = value
        self._mark_schedule_touched()
        if value == "reminder":
            self.time_enabled.setChecked(True)
            self.important_reminder_check.setChecked(True)
        self._refresh_event_type()

    def _refresh_event_type(self) -> None:
        reminder_event = self._event_type == "reminder"
        self.event_type_buttons[self._event_type].setChecked(True)
        self.event_type_box.setVisible(False)
        self.steps_editor.setVisible(self.steps_editor.row_count() > 0)
        self.add_step_button.setVisible(True)
        self.important_reminder_check.setVisible(True)
        self.reminder_summary.setText("软件会在右下角置顶提醒；关闭提醒不会完成事项，需手动关闭。")
        self.reminder_summary.setVisible(True)
        self.reminder_event_quick.setVisible(False)
        self.import_steps_rail.setVisible(True)
        self.switch_to_reminder_button.setVisible(False)
        self.recurrence_box.setVisible(False)
        self._refresh_reminder_details()
        self._refresh_step_layout()

    def _apply_reminder_quick(self, value: str) -> None:
        now = QTime.currentTime()
        if value == "later_today":
            hour = min(22, max(7, now.hour() + 1))
            self.date_edit.setDate(QDate.currentDate())
        elif value == "tomorrow":
            hour = 9
            self.date_edit.setDate(QDate.currentDate().addDays(1))
        elif value == "next_monday":
            days = (8 - QDate.currentDate().dayOfWeek()) % 7 or 7
            hour = 9
            self.date_edit.setDate(QDate.currentDate().addDays(days))
        else:
            self.date_edit.setFocus()
            return
        self.time_enabled.setChecked(True)
        self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(hour)))
        self.minute_combo.setCurrentIndex(max(0, self.minute_combo.findData(0)))
        self._mark_schedule_touched()

    def _refresh_recurrence_details(self, *_unused) -> None:
        self.recurrence_custom.setVisible(self.recurrence_combo.currentData() == "custom")

    def duplicate_requested(self) -> bool:
        return self._duplicate_requested

    def _accept_as_follow_up(self) -> None:
        """Confirm the non-destructive path before turning Save into a copy."""
        if not self.title_edit.toPlainText().strip():
            self.title_edit.setFocus()
            return
        answer = QMessageBox.question(
            self,
            "保留原事项，另建后续",
            "原事项会保留；将另建一条相同内容的后续事项。\n新事项可单独继续修改，分项步骤会从未完成开始。",
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
