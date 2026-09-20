"""Independent schedules for opt-in important reminders."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_HOURS, TIME_MINUTES


class ImportantReminderSchedule(QFrame):
    """Keep the reminder plan independent from an item's planned date/time."""

    changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("importantSchedule")
        self.setStyleSheet(
            "QFrame#importantSchedule { background:#f7faff; border:1px solid #cbd9ee; border-radius:8px; }"
        )
        self._mode = "follow"
        self._task_date = QDate.currentDate()
        self._deadline_target_explicit = False
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(5)
        mode_row.addWidget(QLabel("提醒方式"))
        self.mode_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, label in (("follow", "跟随事项时间"), ("deadline", "目标日提醒"), ("weekly", "周期提醒")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
            )
            button.clicked.connect(lambda _checked=False, value=key: self._set_mode(value))
            group.addButton(button)
            self.mode_buttons[key] = button
            mode_row.addWidget(button)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.follow_panel = QWidget()
        follow = QHBoxLayout(self.follow_panel)
        follow.setContentsMargins(0, 0, 0, 0)
        follow.setSpacing(5)
        follow.addWidget(QLabel("提醒时间"))
        self.offset_buttons: dict[int, QPushButton] = {}
        offset_group = QButtonGroup(self)
        offset_group.setExclusive(True)
        for minutes, label in ((0, "准点"), (10, "提前 10 分"), (30, "提前半小时")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
            )
            button.clicked.connect(lambda _checked=False, value=minutes: self._set_offset(value))
            offset_group.addButton(button)
            self.offset_buttons[minutes] = button
            follow.addWidget(button)
        self.custom_offset = NoWheelComboBox()
        self.custom_offset.setObjectName("reminderOffsetCombo")
        self.custom_offset.addItem("自定义 ▾", None)
        for hours in range(1, 5):
            self.custom_offset.addItem(f"提前 {hours} 小时", hours * 60)
        self.custom_offset.setStyleSheet(
            "QComboBox#reminderOffsetCombo { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
            "QComboBox#reminderOffsetCombo:on { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
        )
        self.custom_offset.currentIndexChanged.connect(self._set_custom_offset)
        follow.addWidget(self.custom_offset)
        follow.addStretch()
        layout.addWidget(self.follow_panel)

        self.deadline_panel = QWidget()
        deadline = QHBoxLayout(self.deadline_panel)
        deadline.setContentsMargins(0, 0, 0, 0)
        deadline.setSpacing(5)
        deadline.addWidget(QLabel("目标日期"))
        self.deadline_target = CompactDatePicker()
        self.deadline_target.setDate(self._task_date)
        deadline.addWidget(self.deadline_target)
        self.deadline_start_label = QLabel()
        deadline.addWidget(self.deadline_start_label)
        self.lead_days = NoWheelComboBox()
        for days in (0, 1, 3, 7, 14):
            self.lead_days.addItem(f"提前 {days} 天" if days else "当天开始", days)
        self.lead_days.currentIndexChanged.connect(self._on_changed)
        deadline.addWidget(self.lead_days)
        deadline.addWidget(QLabel("每天"))
        self.deadline_hour = self._hour_combo()
        self.deadline_minute = self._minute_combo()
        deadline.addWidget(self.deadline_hour)
        deadline.addWidget(self.deadline_minute)
        deadline.addWidget(QLabel("提醒"))
        deadline.addStretch()
        layout.addWidget(self.deadline_panel)
        self.deadline_hint = QLabel("目标日过后仍会每天提醒，直到你取消重要提醒。")
        self.deadline_hint.setStyleSheet("font-size:11px; color:#718096; padding-left:4px;")
        layout.addWidget(self.deadline_hint)

        self.weekly_panel = QWidget()
        weekly = QVBoxLayout(self.weekly_panel)
        weekly.setContentsMargins(0, 0, 0, 0)
        weekly.setSpacing(5)
        weekly_time_row = QHBoxLayout()
        weekly_time_row.setContentsMargins(0, 0, 0, 0)
        weekly_time_row.setSpacing(5)
        weekly_time_row.addWidget(QLabel("开始于"))
        self.weekly_start = CompactDatePicker()
        self.weekly_start.setDate(QDate.currentDate())
        weekly_time_row.addWidget(self.weekly_start)
        weekly_time_row.addWidget(QLabel("提醒时间"))
        self.weekly_hour = self._hour_combo()
        self.weekly_minute = self._minute_combo()
        weekly_time_row.addWidget(self.weekly_hour)
        weekly_time_row.addWidget(self.weekly_minute)
        weekly_time_row.addWidget(QLabel("提醒"))
        weekly_time_row.addStretch()
        weekly.addLayout(weekly_time_row)

        weekly_frequency_row = QHBoxLayout()
        weekly_frequency_row.setContentsMargins(0, 0, 0, 0)
        weekly_frequency_row.setSpacing(5)
        weekly_frequency_row.addWidget(QLabel("重复频率"))
        self.repeat_frequency = NoWheelComboBox()
        for label, unit, interval in (
            ("每天", "day", 1), ("每周", "week", 1), ("每两周", "week", 2),
            ("每月", "month", 1), ("每年", "year", 1), ("自定义", "custom", 0),
        ):
            self.repeat_frequency.addItem(label, (unit, interval))
        self.repeat_frequency.currentIndexChanged.connect(self._on_repeat_frequency_changed)
        weekly_frequency_row.addWidget(self.repeat_frequency)
        self.weekday_label = QLabel("星期")
        weekly_frequency_row.addWidget(self.weekday_label)
        self.weekday = NoWheelComboBox()
        for day, label in enumerate(("周一", "周二", "周三", "周四", "周五", "周六", "周日"), 1):
            self.weekday.addItem(label, day)
        weekly_frequency_row.addWidget(self.weekday)
        weekly_frequency_row.addStretch()
        weekly.addLayout(weekly_frequency_row)

        self.custom_repeat_row = QWidget()
        custom_repeat = QHBoxLayout(self.custom_repeat_row)
        custom_repeat.setContentsMargins(0, 0, 0, 0)
        custom_repeat.setSpacing(5)
        custom_repeat.addWidget(QLabel("自定义"))
        custom_repeat.addWidget(QLabel("每隔"))
        self.repeat_interval = QSpinBox()
        self.repeat_interval.setRange(1, 99)
        self.repeat_interval.setValue(1)
        self.repeat_interval.setFixedWidth(56)
        self.repeat_interval.valueChanged.connect(self._on_changed)
        custom_repeat.addWidget(self.repeat_interval)
        self.repeat_unit = NoWheelComboBox()
        for label, unit in (("天", "day"), ("周", "week"), ("月", "month"), ("年", "year")):
            self.repeat_unit.addItem(label, unit)
        self.repeat_unit.currentIndexChanged.connect(self._on_repeat_frequency_changed)
        custom_repeat.addWidget(self.repeat_unit)
        custom_repeat.addWidget(QLabel("提醒"))
        custom_repeat.addStretch()
        weekly.addWidget(self.custom_repeat_row)
        layout.addWidget(self.weekly_panel)
        self.weekly_hint = QLabel("提醒时间独立于事项日期和事项时间；会按所选频率持续提醒，直到你取消重要提醒。")
        self.weekly_hint.setStyleSheet("font-size:11px; color:#718096; padding-left:4px;")
        layout.addWidget(self.weekly_hint)

        for widget in (self.deadline_hour, self.deadline_minute, self.weekly_start, self.weekday, self.weekly_hour, self.weekly_minute):
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self._on_changed)
        self.weekly_start.dateChanged.connect(self._on_changed)
        self.deadline_target.dateChanged.connect(self._on_deadline_target_changed)
        self._set_offset(0, emit=False)
        self._on_repeat_frequency_changed(emit=False)
        self._set_mode("follow", emit=False)

    @staticmethod
    def _hour_combo() -> NoWheelComboBox:
        combo = NoWheelComboBox()
        for hour in TIME_HOURS:
            combo.addItem(f"{hour:02d} 时", hour)
        # Native Windows combobox arrows and CJK glyphs need more room than
        # macOS. Keep time fields readable rather than letting text clip.
        combo.setFixedWidth(88)
        return combo

    @staticmethod
    def _minute_combo() -> NoWheelComboBox:
        combo = NoWheelComboBox()
        for minute in TIME_MINUTES:
            combo.addItem(f"{minute:02d} 分", minute)
        combo.setFixedWidth(88)
        return combo

    def set_task_date(self, value: QDate) -> None:
        self._task_date = value
        if not self._deadline_target_explicit:
            self.deadline_target.setDate(value)
        self._refresh_deadline_copy()

    def _on_deadline_target_changed(self, *_unused) -> None:
        if not self._loading:
            self._deadline_target_explicit = True
            self._refresh_deadline_copy()
            self.changed.emit()

    def set_task_time_available(self, available: bool) -> None:
        button = self.mode_buttons["follow"]
        button.setEnabled(available)
        button.setToolTip("先勾选事项时间，才能按事项时间提醒" if not available else "按事项时间提醒")
        if not available and self._mode == "follow":
            self._set_mode("deadline", emit=not self._loading)

    def _refresh_deadline_copy(self) -> None:
        today = QDate.currentDate()
        if self.deadline_target.date() > today:
            self.deadline_start_label.setText("提醒从")
            self.lead_days.setVisible(True)
        else:
            self.deadline_start_label.setText("从今天起往后")
            self.lead_days.setVisible(False)

    def _set_mode(self, mode: str, *, emit: bool = True) -> None:
        self._mode = mode if mode in {"follow", "deadline", "weekly"} else "follow"
        self.mode_buttons[self._mode].setChecked(True)
        self.follow_panel.setVisible(self._mode == "follow")
        self.deadline_panel.setVisible(self._mode == "deadline")
        self.deadline_hint.setVisible(self._mode == "deadline")
        self.weekly_panel.setVisible(self._mode == "weekly")
        self.weekly_hint.setVisible(self._mode == "weekly")
        self._refresh_deadline_copy()
        self.updateGeometry()
        if emit:
            self.changed.emit()

    def _on_repeat_frequency_changed(self, *_unused, emit: bool = True) -> None:
        unit, _interval = self.repeat_frequency.currentData() or ("week", 1)
        custom = unit == "custom"
        if custom:
            unit = self.repeat_unit.currentData() or "week"
        show_weekday = unit == "week"
        self.weekday_label.setVisible(show_weekday)
        self.weekday.setVisible(show_weekday)
        self.custom_repeat_row.setVisible(custom)
        self.weekly_panel.updateGeometry()
        self.updateGeometry()
        if emit and not self._loading:
            self.changed.emit()

    def _repeat_values(self) -> tuple[str, int]:
        unit, interval = self.repeat_frequency.currentData() or ("week", 1)
        if unit == "custom":
            return str(self.repeat_unit.currentData() or "week"), self.repeat_interval.value()
        return str(unit), max(1, int(interval))

    def _repeat_preset_index(self, unit: str, interval: int) -> int:
        for index in range(self.repeat_frequency.count()):
            if self.repeat_frequency.itemData(index) == (unit, interval):
                return index
        return -1

    def _set_offset(self, minutes: int, *, emit: bool = True) -> None:
        self._offset_minutes = minutes
        for value, button in self.offset_buttons.items():
            button.setChecked(value == minutes)
        self.custom_offset.blockSignals(True)
        self.custom_offset.setCurrentIndex(0)
        self.custom_offset.blockSignals(False)
        self.custom_offset.setStyleSheet(
            "QComboBox#reminderOffsetCombo { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
            "QComboBox#reminderOffsetCombo:on { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
        )
        if emit:
            self.changed.emit()

    def _set_custom_offset(self, index: int) -> None:
        minutes = self.custom_offset.itemData(index)
        if not minutes:
            return
        self._offset_minutes = int(minutes)
        for button in self.offset_buttons.values():
            button.setChecked(False)
        # The combobox itself is the selected, blue control.
        self.custom_offset.setStyleSheet(
            "QComboBox#reminderOffsetCombo { border:1px solid #5d82bb; border-radius:7px; color:#fff; background:#5d82bb; padding:5px 8px; font-size:11px; }"
        )
        if not self._loading:
            self.changed.emit()

    def _on_changed(self, *_unused) -> None:
        if not self._loading:
            self.changed.emit()

    def load(self, task) -> None:
        self._loading = True
        mode = task["important_reminder_mode"] if "important_reminder_mode" in task.keys() else "follow"
        self.set_task_date(QDate.fromString(task["task_date"], "yyyy-MM-dd"))
        target = task["important_reminder_target_date"] if "important_reminder_target_date" in task.keys() else None
        self._deadline_target_explicit = bool(target)
        self.deadline_target.setDate(QDate.fromString(str(target or task["task_date"]), "yyyy-MM-dd"))
        self._set_mode(str(mode), emit=False)
        offset = int(task["important_reminder_offset_minutes"] or 0) if "important_reminder_offset_minutes" in task.keys() else 0
        if offset in self.offset_buttons:
            self._set_offset(offset, emit=False)
        else:
            index = self.custom_offset.findData(offset)
            self.custom_offset.setCurrentIndex(max(1, index))
        lead = int(task["important_reminder_lead_days"] or 0) if "important_reminder_lead_days" in task.keys() else 0
        self.lead_days.setCurrentIndex(max(0, self.lead_days.findData(lead)))
        start = task["important_reminder_start_date"] if "important_reminder_start_date" in task.keys() else None
        self.weekly_start.setDate(QDate.fromString(str(start or task["task_date"]), "yyyy-MM-dd"))
        weekday = int(task["important_reminder_weekday"] or 1) if "important_reminder_weekday" in task.keys() else 1
        self.weekday.setCurrentIndex(max(0, self.weekday.findData(weekday)))
        repeat_unit = str(task["important_reminder_repeat_unit"] or "week") if "important_reminder_repeat_unit" in task.keys() else "week"
        repeat_interval = max(1, int(task["important_reminder_repeat_interval"] or 1)) if "important_reminder_repeat_interval" in task.keys() else 1
        preset_index = self._repeat_preset_index(repeat_unit, repeat_interval)
        if preset_index >= 0:
            self.repeat_frequency.setCurrentIndex(preset_index)
        else:
            self.repeat_frequency.setCurrentIndex(self._repeat_preset_index("custom", 0))
            self.repeat_unit.setCurrentIndex(max(0, self.repeat_unit.findData(repeat_unit)))
            self.repeat_interval.setValue(repeat_interval)
        reminder_time = task["important_reminder_time"] if "important_reminder_time" in task.keys() else None
        if reminder_time:
            hour, minute = str(reminder_time).split(":", 1)
            for combo, value in ((self.deadline_hour, int(hour)), (self.weekly_hour, int(hour)), (self.deadline_minute, int(minute)), (self.weekly_minute, int(minute))):
                combo.setCurrentIndex(max(0, combo.findData(value)))
        self._loading = False
        self._refresh_deadline_copy()
        self._on_repeat_frequency_changed(emit=False)

    def values(self) -> dict:
        if self._mode == "follow":
            reminder_time = None
            start_date = None
            target_date = None
            weekday = None
            lead_days = 0
        elif self._mode == "deadline":
            reminder_time = f"{self.deadline_hour.currentData():02d}:{self.deadline_minute.currentData():02d}"
            start_date = None
            target_date = self.deadline_target.date().toString("yyyy-MM-dd")
            weekday = None
            lead_days = int(self.lead_days.currentData() or 0)
        else:
            reminder_time = f"{self.weekly_hour.currentData():02d}:{self.weekly_minute.currentData():02d}"
            start_date = self.weekly_start.date().toString("yyyy-MM-dd")
            target_date = None
            weekday = int(self.weekday.currentData())
            lead_days = 0
            repeat_unit, repeat_interval = self._repeat_values()
        if self._mode != "weekly":
            repeat_unit, repeat_interval = "week", 1
        return {
            "important_reminder_mode": self._mode,
            "important_reminder_offset_minutes": self._offset_minutes if self._mode == "follow" else 0,
            "important_reminder_start_date": start_date,
            "important_reminder_target_date": target_date,
            "important_reminder_time": reminder_time,
            "important_reminder_lead_days": lead_days,
            "important_reminder_weekday": weekday,
            "important_reminder_repeat_unit": repeat_unit,
            "important_reminder_repeat_interval": repeat_interval,
            "important_reminder_at": None,
        }


class ImportantReminderEditorDialog(QDialog):
    """A focused editor for an important reminder plan, separate from a to-do."""

    def __init__(self, task_date: QDate, values: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("重要提醒")
        self.setMinimumWidth(600)
        self.setStyleSheet("QDialog { background:#f7f9fc; }")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        back = QPushButton("← 切回普通待办")
        back.setObjectName("quietButton")
        back.clicked.connect(self.reject)
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)
        title = QLabel("重要提醒设置")
        title.setStyleSheet("font-size:18px; font-weight:600; color:#2c3a4d;")
        layout.addWidget(title)
        hint = QLabel("提醒计划独立于事项日期和事项时间；保存后会持续提醒，直到你取消重要提醒。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:12px; color:#718096;")
        layout.addWidget(hint)
        self.schedule = ImportantReminderSchedule()
        self.schedule.load({
            "task_date": task_date.toString("yyyy-MM-dd"),
            **values,
        })
        layout.addWidget(self.schedule)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("完成提醒设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.schedule.changed.connect(self._adjust_to_schedule)

    def _adjust_to_schedule(self) -> None:
        """Reclaim hidden mode rows before the next native-layout pass."""
        QTimer.singleShot(0, self.adjustSize)

    def values(self) -> dict:
        return self.schedule.values()
