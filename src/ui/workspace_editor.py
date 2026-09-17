"""Right-hand, save-first editor used by the full-screen workspace."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QTime, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_HOURS, TIME_MINUTES, normalize_note_text
from ui.important_schedule import ImportantReminderEditorDialog, ImportantReminderSchedule
from ui.task_dialog import PlainNotesEditor, TitleEditor
from ui.task_steps import CompactStepStartButton, TaskStepsEditor


class WorkspaceEditor(QWidget):
    """An editor that never writes until its explicit Save button is used."""

    save_requested = pyqtSignal(int, dict)
    duplicate_requested = pyqtSignal(int)
    move_today_requested = pyqtSignal(int)
    cancel_important_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._task_id: int | None = None
        self._baseline: dict | None = None
        self._loading = False
        self._task_is_previous = False
        self._reminder_basis = "task_time"
        self._reminder_choice = "offset:0"
        self._from_now_target: str | None = None
        self._legacy_reminder_at: str | None = None
        self._schedule_touched = False
        self._event_type = "todo"

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
        form.setSpacing(4)

        self.title_edit = TitleEditor()
        # Windows is the layout baseline. A compact two-line title reserves
        # enough room without creating a large dead band below one-line text.
        self.title_edit.setFixedHeight(56)
        self.title_edit.setPlaceholderText("事项标题（最多两行）")
        self.title_edit.setToolTip("事项标题最多两行；Enter 转到具体内容；Shift + Enter 可换行。")
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

        self.notes_edit = PlainNotesEditor()
        self.notes_edit.setPlaceholderText("具体事项、材料或下一步")
        self.notes_edit.setMinimumHeight(170)
        self.notes_edit.setAcceptRichText(False)
        # The target must exist before TitleEditor can wire Enter to it.
        self.title_edit.next_field_requested.connect(self.notes_edit.setFocus)
        self.steps_editor = TaskStepsEditor()
        self.steps_editor.use_external_start_button()
        self.steps_editor.next_field_requested.connect(self.notes_edit.setFocus)
        self.notes_section = QWidget()
        notes_layout = QVBoxLayout(self.notes_section)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(3)
        notes_header = QHBoxLayout()
        notes_header.setContentsMargins(0, 0, 0, 0)
        notes_label = QLabel("具体内容")
        notes_label.setStyleSheet("font-size:12px; color:#718096; font-weight:600;")
        notes_header.addWidget(notes_label)
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
        self.import_steps_rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
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

        self.windows_reminder_box = QFrame()
        self.windows_reminder_box.setObjectName("windowsReminderBox")
        self.windows_reminder_box.setStyleSheet(
            "QFrame#windowsReminderBox { border:1px solid #d5e0ef; border-radius:8px; background:#fafcff; }"
        )
        reminder_layout = QVBoxLayout(self.windows_reminder_box)
        reminder_layout.setContentsMargins(9, 7, 9, 7)
        reminder_layout.setSpacing(5)
        reminder_content = QWidget()
        reminder_content_row = QHBoxLayout(reminder_content)
        reminder_content_row.setContentsMargins(0, 0, 0, 0)
        reminder_content_row.setSpacing(12)
        reminder_left = QWidget()
        reminder_left.setObjectName("importantReminderQuickArea")
        self._reminder_left_layout = QVBoxLayout(reminder_left)
        self._reminder_left_layout.setContentsMargins(0, 0, 0, 0)
        self._reminder_left_layout.setSpacing(5)
        reminder_content_row.addWidget(reminder_left, 1)
        reminder_layout.addWidget(reminder_content)
        self.important_reminder_check = QCheckBox("启用重要提醒")
        self.important_reminder_check.setToolTip("勾选后，软件会在右下角显示置顶提醒；提醒可关闭或稍后提醒。")
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
        self.reminder_summary.setStyleSheet("font-size:11px; color:#718096; padding-left:23px;")
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
        self.important_schedule.set_task_date(self.date_edit.date())
        self.important_schedule.changed.connect(self._mark_schedule_touched)
        self.important_schedule.changed.connect(self._refresh_status)
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
        self.time_enabled.toggled.connect(self._sync_windows_reminder_availability)
        self.important_reminder_check.toggled.connect(self._sync_windows_reminder_availability)
        self.important_reminder_check.toggled.connect(self._refresh_reminder_details)
        self.date_edit.dateChanged.connect(self.important_schedule.set_task_date)
        self._choose_reminder(self._reminder_choice, touched=False)
        self._choose_reminder_basis(self._reminder_basis)
        self.fixed_check = QCheckBox("固定锁住待办（显示在当天列表最底部）")

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

        form.addWidget(self.title_edit)
        form.addWidget(self.steps_editor)
        # The body is the only flexible area. It takes spare vertical room;
        # controls above and below never shift because optional actions exist.
        form.addWidget(self.notes_section, 1)
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
        form.addWidget(self.windows_reminder_box)
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
        recurrence_layout.addWidget(self.recurrence_combo)
        self.recurrence_custom = QWidget()
        recurrence_custom_layout = QHBoxLayout(self.recurrence_custom)
        recurrence_custom_layout.setContentsMargins(0, 0, 0, 0)
        recurrence_custom_layout.setSpacing(4)
        recurrence_custom_layout.addWidget(QLabel("每"))
        self.recurrence_interval_spin = QSpinBox()
        self.recurrence_interval_spin.setRange(1, 99)
        self.recurrence_interval_spin.setFixedWidth(48)
        recurrence_custom_layout.addWidget(self.recurrence_interval_spin)
        self.recurrence_unit_combo = NoWheelComboBox()
        for label, unit in (("天", "day"), ("周", "week"), ("月", "month"), ("年", "year")):
            self.recurrence_unit_combo.addItem(label, unit)
        recurrence_custom_layout.addWidget(self.recurrence_unit_combo)
        recurrence_layout.addWidget(self.recurrence_custom)
        recurrence_layout.addStretch()
        self.operation_divider = QFrame()
        self.operation_divider.setFrameShape(QFrame.Shape.HLine)
        self.operation_divider.setStyleSheet("color:#dbe4ee; margin:13px 0 7px;")
        form.addWidget(self.operation_divider)
        self.operations_label = QLabel("事项操作")
        self.operations_label.setStyleSheet("font-size:12px; color:#718096; font-weight:600; padding:0 0 5px;")
        form.addWidget(self.operations_label)
        self.duplicate_button = QPushButton("保留原事项，另建后续")
        self.duplicate_button.setObjectName("continuationAction")
        self.duplicate_button.setFixedHeight(34)
        self.duplicate_button.setStyleSheet(
            "QPushButton#continuationAction { text-align:left; padding:5px 10px; min-height:22px; max-height:22px; "
            "background:#f7faff; border:1px solid #a9c1e4; border-radius:8px; color:#426b9f; font-size:13px; font-weight:600; }"
            "QPushButton#continuationAction:hover { background:#edf4ff; border-color:#759ad1; }"
            "QPushButton#continuationAction:disabled { color:#9aa7b7; background:#f8fafc; border-color:#dce4ee; }"
        )
        self.duplicate_button.setToolTip("保留原事项，新建一条可继续处理的后续事项。")
        self.duplicate_button.clicked.connect(self._emit_duplicate)
        self.duplicate_hint = QLabel("原事项会保留；新事项可继续处理，分项进度重新开始。")
        self.duplicate_hint.setWordWrap(True)
        self.duplicate_hint.setStyleSheet("font-size:11px; color:#7f8da0; padding:1px 5px 3px;")
        self.move_today_button = QPushButton("安排到今天继续处理")
        self.move_today_button.setObjectName("continuationAction")
        self.move_today_button.setFixedHeight(34)
        self.move_today_button.setStyleSheet(
            "QPushButton#continuationAction { text-align:left; padding:5px 10px; min-height:22px; max-height:22px; "
            "background:#f7faff; border:1px solid #a9c1e4; border-radius:8px; color:#426b9f; font-size:13px; font-weight:600; }"
            "QPushButton#continuationAction:hover { background:#edf4ff; border-color:#759ad1; }"
        )
        self.move_today_button.setToolTip("直接把原事项改期到今天，不会新建副本。")
        self.move_today_button.clicked.connect(self._emit_move_today)
        self.move_today_hint = QLabel("直接把原事项日期改为今天，不会新建副本。")
        self.move_today_hint.setWordWrap(True)
        self.move_today_hint.setStyleSheet("font-size:11px; color:#7f8da0; padding:1px 5px 3px;")
        self.cancel_important_button = QPushButton("取消重要提醒")
        self.cancel_important_button.setObjectName("continuationAction")
        self.cancel_important_button.setToolTip("停止这条重要提醒，不会完成或删除事项。")
        self.cancel_important_button.clicked.connect(self._emit_cancel_important)
        form.addWidget(self.duplicate_button)
        form.addWidget(self.duplicate_hint)
        form.addWidget(self.move_today_button)
        form.addWidget(self.move_today_hint)
        form.addWidget(self.cancel_important_button)
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
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.steps_editor.changed.connect(self._on_steps_changed)
        self.date_edit.dateChanged.connect(self._refresh_status)
        self.time_enabled.toggled.connect(self._refresh_status)
        self.hour_combo.currentIndexChanged.connect(self._refresh_status)
        self.minute_combo.currentIndexChanged.connect(self._refresh_status)
        self.important_reminder_check.toggled.connect(self._refresh_status)
        self.recurrence_combo.currentIndexChanged.connect(self._refresh_recurrence_details)
        self.recurrence_combo.currentIndexChanged.connect(self._refresh_status)
        self.recurrence_interval_spin.valueChanged.connect(self._refresh_status)
        self.recurrence_unit_combo.currentIndexChanged.connect(self._refresh_status)
        self.fixed_check.toggled.connect(self._refresh_status)
        self._refresh_recurrence_details()
        self._refresh_event_type()
        self.clear()

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
        dialog = ImportantReminderEditorDialog(self.date_edit.date(), self.important_schedule.values(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.important_schedule.load({
                "task_date": self.date_edit.date().toString("yyyy-MM-dd"),
                **dialog.values(),
            })
            self.important_reminder_check.setChecked(True)
            self._mark_schedule_touched()
            self._refresh_reminder_details()
            self._refresh_status()

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
        mode = values["important_reminder_mode"]
        complex_plan = self.important_reminder_check.isChecked() and mode in {"deadline", "weekly"}
        offset = (
            values["important_reminder_offset_minutes"]
            if self.important_reminder_check.isChecked() and mode == "follow"
            else None
        )
        for minutes, button in self.quick_reminder_buttons.items():
            button.setChecked(offset == minutes)
            button.setEnabled(not complex_plan)
        self.quick_reminder_custom.blockSignals(True)
        index = self.quick_reminder_custom.findData(offset) if offset not in self.quick_reminder_buttons and offset else 0
        self.quick_reminder_custom.setCurrentIndex(index)
        self.quick_reminder_custom.blockSignals(False)
        self.quick_reminder_custom.setEnabled(not complex_plan)
        if complex_plan:
            plan_name = "目标日提醒" if mode == "deadline" else "周期提醒"
            self.quick_reminder_notice.setText(f"已启用{plan_name}；简单提醒不可叠加，请在“重要提醒设置”中修改。")
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

    def _choose_custom_offset(self, index: int) -> None:
        if index <= 0:
            return
        self._reminder_choice = "custom"
        for button in self.reminder_choice_buttons.values():
            button.setChecked(False)
        self._mark_schedule_touched()
        self._refresh_reminder_details()

    def _choose_reminder_basis(self, value: str) -> None:
        self._reminder_basis = value
        self.reminder_basis_buttons[value].setChecked(True)
        self._refresh_reminder_details()

    def _mark_schedule_touched(self, *_unused) -> None:
        self._schedule_touched = True
        self._legacy_reminder_at = None
        if not self._loading:
            self._refresh_status()

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
        self.switch_to_reminder_button.setVisible(not reminder_event)
        self.reminder_summary.setText(
            "软件会在右下角置顶提醒；关闭提醒不会完成事项，需手动关闭。"
        )
        self.reminder_event_quick.setVisible(False)
        self.import_steps_rail.setVisible(True)
        self.switch_to_reminder_button.setVisible(False)
        self.recurrence_box.setVisible(False)
        self._refresh_reminder_details()
        self._update_editor_layout()

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
        self._refresh_status()

    def _refresh_recurrence_details(self, *_unused) -> None:
        self.recurrence_custom.setVisible(self.recurrence_combo.currentData() == "custom")

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
            "原事项会保留；新事项可继续处理，分项进度重新开始。"
            if can_copy else "请先保存当前修改后，再选择继续处理方式。"
        )

    def _on_notes_changed(self) -> None:
        self._refresh_import_button()
        self._update_editor_layout()
        self._refresh_status()

    def _on_steps_changed(self) -> None:
        self._update_editor_layout()
        self._refresh_status()

    def _update_editor_layout(self) -> None:
        """Let the body own spare room; long text expands the outer editor."""
        # A long body grows the workspace's single outer scroll area instead
        # of creating a second, nested text-editor scrollbar.
        content_height = self.notes_edit.document().blockCount() * 24 + 30
        self.notes_edit.setMaximumHeight(16777215)
        self.notes_edit.setMinimumHeight(max(170, content_height))
        # The split tool is an extension of the body editor, so its outside
        # frame always shares the body editor's exact height.
        self.import_steps_rail.setMinimumHeight(self.notes_edit.minimumHeight())

    def _import_note_lines(self) -> None:
        text = self.notes_edit.toPlainText()
        imported = self.steps_editor.import_note_lines(text)
        if imported:
            self._refresh_status()
            self._refresh_import_button()

    def _refresh_import_button(self) -> None:
        text = self.notes_edit.toPlainText()
        line_count = len([line for line in text.splitlines() if line.strip()])
        can_split = line_count >= 2
        self.import_steps_rail.setVisible(can_split)
        self.import_steps_button.setEnabled(can_split)
        self.import_steps_button.setText("⇩\n拆成步骤")

    def _emit_duplicate(self) -> None:
        if self._task_id is not None and not self.is_dirty():
            self.duplicate_requested.emit(self._task_id)

    def _emit_move_today(self) -> None:
        if self._task_id is not None and self._task_is_previous:
            self.move_today_requested.emit(self._task_id)

    def _emit_cancel_important(self) -> None:
        if self._task_id is not None:
            self.cancel_important_requested.emit(self._task_id)

    def clear(self) -> None:
        self._loading = True
        self._task_id = None
        self._baseline = None
        self._task_is_previous = False
        self.heading.setText("选择一条事项")
        self.hint.setText("从中间列表选择后可直接修改；只有点击保存才会生效。")
        self.title_edit.clear()
        self.notes_edit.clear()
        self.time_enabled.setChecked(False)
        self.important_reminder_check.setChecked(False)
        self._from_now_target = None
        self._legacy_reminder_at = None
        self._schedule_touched = False
        self._event_type = "todo"
        self._reminder_basis = "task_time"
        self._choose_reminder("offset:0")
        self._choose_reminder_basis("task_time")
        self.custom_offset_combo.setCurrentIndex(0)
        self.important_schedule.set_task_date(self.date_edit.date())
        self._schedule_touched = False
        self.recurrence_combo.setCurrentIndex(0)
        self.recurrence_interval_spin.setValue(1)
        self._sync_windows_reminder_availability(False)
        self.fixed_check.setChecked(False)
        self.steps_editor.set_steps([])
        self._loading = False
        self._refresh_event_type()
        self._update_editor_layout()
        self.form_host.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.duplicate_button.setEnabled(False)
        self.operation_divider.setVisible(False)
        self.operations_label.setVisible(False)
        self.duplicate_button.setVisible(False)
        self.duplicate_hint.setVisible(False)
        self.move_today_button.setVisible(False)
        self.move_today_hint.setVisible(False)
        self.cancel_important_button.setVisible(False)
        self._refresh_import_button()
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
        reminder_enabled = bool(supports_reminder and task["windows_reminder_enabled"])
        offset = int(task["important_reminder_offset_minutes"]) if "important_reminder_offset_minutes" in task.keys() else 0
        self.important_reminder_check.setChecked(reminder_enabled)
        reminder_at = task["important_reminder_at"] if "important_reminder_at" in task.keys() else None
        self._legacy_reminder_at = str(reminder_at) if reminder_at else None
        self._schedule_touched = False
        self._event_type = task["event_type"] if "event_type" in task.keys() else "todo"
        self.important_schedule.load(task)
        if reminder_at:
            self._from_now_target = str(reminder_at)
            self._choose_reminder_basis("task_time")
            self._choose_reminder("offset:0", touched=False)
        else:
            self._from_now_target = None
            self._choose_reminder_basis("task_time")
            choice = f"offset:{offset}" if f"offset:{offset}" in self.reminder_choice_buttons else "custom"
            self._choose_reminder(choice, touched=False)
            if choice == "custom":
                self.custom_offset_combo.setCurrentIndex(max(1, self.custom_offset_combo.findData(offset)))
        recurrence_unit = task["recurrence_unit"] if "recurrence_unit" in task.keys() else "none"
        recurrence_interval = int(task["recurrence_interval"] or 1) if "recurrence_interval" in task.keys() else 1
        self.recurrence_combo.setCurrentIndex(max(0, self.recurrence_combo.findData(recurrence_unit)))
        self.recurrence_interval_spin.setValue(recurrence_interval)
        self.recurrence_unit_combo.setCurrentIndex(max(0, self.recurrence_unit_combo.findData(recurrence_unit if recurrence_unit != "none" else "day")))
        self._sync_windows_reminder_availability(bool(due))
        self.fixed_check.setChecked(bool(task["is_fixed"]))
        self._loading = False
        self._refresh_event_type()
        self._update_editor_layout()
        self._refresh_import_button()
        self.form_host.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.operation_divider.setVisible(True)
        self.operations_label.setVisible(True)
        self.duplicate_button.setVisible(True)
        self.duplicate_hint.setVisible(True)
        self.move_today_button.setVisible(self._task_is_previous)
        self.move_today_hint.setVisible(self._task_is_previous)
        reminder_mode = task["important_reminder_mode"] if "important_reminder_mode" in task.keys() else "follow"
        self.cancel_important_button.setVisible(
            bool(task["windows_reminder_enabled"]) and reminder_mode in {"deadline", "weekly"}
        )
        self.operations_label.setText("继续处理方式" if self._task_is_previous else "事项操作")
        self._baseline = self.values()
        self._refresh_status()

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
            "recurrence_unit": self.recurrence_unit_combo.currentData() if self.recurrence_combo.currentData() == "custom" else self.recurrence_combo.currentData(),
            "recurrence_interval": self.recurrence_interval_spin.value() if self.recurrence_combo.currentData() == "custom" else 1,
            "steps": self.steps_editor.values(),
            "content_mode": "notes",
            "event_type": self._event_type,
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
        self.date_edit.setDate(QDate.fromString(values["task_date"], "yyyy-MM-dd"))
        self.time_enabled.setChecked(bool(values["due_time"]))
        if values["due_time"]:
            hour, minute = values["due_time"].split(":", 1)
            self.hour_combo.setCurrentIndex(max(0, self.hour_combo.findData(int(hour))))
            self.minute_combo.setCurrentIndex(max(0, self.minute_combo.findData(int(minute))))
        self.important_reminder_check.setChecked(values["windows_reminder_enabled"])
        reminder_at = values.get("important_reminder_at")
        self._legacy_reminder_at = reminder_at
        self._schedule_touched = False
        self._event_type = values.get("event_type", "todo")
        self.important_schedule.load(values)
        if reminder_at:
            self._from_now_target = reminder_at
            self._choose_reminder_basis("task_time")
            self._choose_reminder("offset:0", touched=False)
        else:
            self._from_now_target = None
            self._choose_reminder_basis("task_time")
            offset = values.get("important_reminder_offset_minutes", 0)
            choice = f"offset:{offset}" if f"offset:{offset}" in self.reminder_choice_buttons else "custom"
            self._choose_reminder(choice, touched=False)
            if choice == "custom":
                self.custom_offset_combo.setCurrentIndex(max(1, self.custom_offset_combo.findData(offset)))
        unit = values.get("recurrence_unit", "none")
        self.recurrence_combo.setCurrentIndex(max(0, self.recurrence_combo.findData(unit)))
        self.recurrence_interval_spin.setValue(values.get("recurrence_interval", 1))
        self.recurrence_unit_combo.setCurrentIndex(max(0, self.recurrence_unit_combo.findData(unit if unit != "none" else "day")))
        self._sync_windows_reminder_availability(bool(values["due_time"]))
        self.fixed_check.setChecked(values["is_fixed"])
        self.steps_editor.set_steps(values.get("steps", []))
        self._loading = False
        self._refresh_event_type()
        self._update_editor_layout()
        self._refresh_import_button()
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
