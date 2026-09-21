"""Independent schedules for opt-in important reminders."""

from __future__ import annotations

from datetime import date
import json

from PyQt6.QtCore import QDate, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox, QStackedWidget, QToolTip, QVBoxLayout, QWidget

from ui.controls import CompactDatePicker, NoWheelComboBox, TIME_COMBO_WIDTH, TIME_HOURS, TIME_MINUTES


class ImportantReminderSchedule(QFrame):
    """Keep the reminder plan independent from an item's planned date/time."""

    changed = pyqtSignal()
    MODES = ("follow", "deadline", "weekly")
    MODE_LABELS = {"follow": "跟随事项时间", "deadline": "目标日提醒", "weekly": "周期提醒"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("importantSchedule")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QFrame#importantSchedule { background:#f7faff; border:1px solid #cbd9ee; border-radius:8px; }"
        )
        self._mode = "follow"
        self._selected_mode: str | None = None
        self._drafts: dict[str, dict] = {mode: {} for mode in self.MODES}
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
        self.mode_cards: dict[str, QWidget] = {}
        for key, label in (("follow", "跟随事项时间"), ("deadline", "目标日提醒"), ("weekly", "周期提醒")):
            card = QFrame()
            card.setObjectName("reminderModeCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(4)
            button = QPushButton(label)
            button.setToolTip("点击查看该提醒方式的设置")
            button.setStyleSheet(
                "QPushButton { border:1px solid #b8cbe7; border-radius:7px; color:#476b9e; background:#fff; padding:5px 8px; font-size:11px; }"
                "QPushButton:hover { background:#f3f7ff; border-color:#7597d1; }"
            )
            button.clicked.connect(lambda _checked=False, value=key: self._view_mode(value, emit=False))
            self.mode_buttons[key] = button
            card_layout.addWidget(button)
            self.mode_cards[key] = card
            mode_row.addWidget(card)
        mode_row.addStretch()
        self.selection_notice = QLabel()
        self.selection_notice.setWordWrap(True)
        self.selection_notice.setStyleSheet("font-size:11px; color:#8a621d; background:#fff8df; border:1px solid #f0dda2; border-radius:7px; padding:5px 8px;")
        self.selection_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selection_notice.setParent(self)
        self.selection_notice.setVisible(False)
        self._hide_selection_notice()

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
        self.deadline_hint = QLabel("目标日过后仍会每天提醒，直到你取消重要提醒。")
        self.deadline_hint.setStyleSheet("font-size:11px; color:#718096; padding-left:4px;")

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
        self.weekly_hint = QLabel("提醒时间独立于事项日期和事项时间；会按所选频率持续提醒，直到你取消重要提醒。")
        self.weekly_hint.setStyleSheet("font-size:11px; color:#718096; padding-left:4px;")
        self._mode_panels = {"follow": self.follow_panel, "deadline": self.deadline_panel, "weekly": self.weekly_panel}

        self._mode_stack = QStackedWidget()
        self._mode_stack.setObjectName("reminderModeStack")
        follow_page = QWidget()
        follow_layout = QVBoxLayout(follow_page)
        follow_layout.setContentsMargins(0, 0, 0, 0)
        follow_layout.addWidget(self.follow_panel)
        follow_layout.addStretch()
        deadline_page = QWidget()
        deadline_layout = QVBoxLayout(deadline_page)
        deadline_layout.setContentsMargins(0, 0, 0, 0)
        deadline_layout.setSpacing(4)
        deadline_layout.addWidget(self.deadline_panel)
        deadline_layout.addWidget(self.deadline_hint)
        deadline_layout.addStretch()
        weekly_page = QWidget()
        weekly_layout = QVBoxLayout(weekly_page)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_layout.setSpacing(4)
        weekly_layout.addWidget(self.weekly_panel)
        weekly_layout.addWidget(self.weekly_hint)
        weekly_layout.addStretch()
        self._mode_pages = {"follow": follow_page, "deadline": deadline_page, "weekly": weekly_page}
        for page in (follow_page, deadline_page, weekly_page):
            self._mode_stack.addWidget(page)

        selection_panel = QFrame()
        selection_panel.setObjectName("reminderSelectionPanel")
        selection_panel.setFixedWidth(135)
        selection_layout = QVBoxLayout(selection_panel)
        selection_layout.setContentsMargins(8, 8, 8, 8)
        selection_layout.setSpacing(5)
        self.selection_button = QPushButton("选中")
        self.selection_button.setCheckable(True)
        self.selection_button.setToolTip("把当前查看的提醒方式设为唯一生效的方式")
        self.selection_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.selection_button.setMinimumHeight(60)
        self.selection_button.setStyleSheet(
            "QPushButton { border:1px solid #9db9df; border-radius:8px; color:#426b9f; background:#fff; padding:8px 12px; font-size:12px; font-weight:600; }"
            "QPushButton:hover { background:#edf4ff; border-color:#6f95cf; }"
            "QPushButton:checked { color:#fff; background:#5d82bb; border-color:#5d82bb; }"
        )
        self.selection_button.clicked.connect(lambda _checked=False: self._select_mode(self._mode))
        selection_layout.addWidget(self.selection_button, 1)
        mode_content = QVBoxLayout()
        mode_content.setContentsMargins(0, 0, 0, 0)
        mode_content.setSpacing(5)
        mode_content.addLayout(mode_row)
        mode_content.addWidget(self._mode_stack, 1)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.addLayout(mode_content, 1)
        body.addWidget(selection_panel, 0)
        layout.addLayout(body)

        for widget in (self.deadline_hour, self.deadline_minute, self.weekly_start, self.weekday, self.weekly_hour, self.weekly_minute):
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self._on_changed)
        self.weekly_start.dateChanged.connect(self._on_changed)
        self.deadline_target.dateChanged.connect(self._on_deadline_target_changed)
        self._set_offset(0, emit=False)
        self._on_repeat_frequency_changed(emit=False)
        self._view_mode("follow", emit=False)
        self._refresh_selection_visuals()

    @staticmethod
    def _hour_combo() -> NoWheelComboBox:
        combo = NoWheelComboBox()
        for hour in TIME_HOURS:
            combo.addItem(f"{hour:02d} 时", hour)
        # Native Windows combobox arrows and CJK glyphs need more room than
        # macOS. Keep time fields readable rather than letting text clip.
        combo.setFixedWidth(TIME_COMBO_WIDTH)
        return combo

    @staticmethod
    def _minute_combo() -> NoWheelComboBox:
        combo = NoWheelComboBox()
        for minute in TIME_MINUTES:
            combo.addItem(f"{minute:02d} 分", minute)
        combo.setFixedWidth(TIME_COMBO_WIDTH)
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
        if not available:
            if self._mode == "follow":
                self.selection_button.setToolTip("先勾选事项时间，才能选中“跟随事项时间”")
            if self._selected_mode == "follow":
                self._selected_mode = None
                self._view_mode("deadline", emit=False)
                self._refresh_selection_visuals()
        else:
            self.selection_button.setToolTip("把当前查看的提醒方式设为唯一生效的方式")

    def _refresh_deadline_copy(self) -> None:
        today = QDate.currentDate()
        if self.deadline_target.date() > today:
            self.deadline_start_label.setText("提醒从")
            self.lead_days.setVisible(True)
        else:
            self.deadline_start_label.setText("从今天起往后")
            self.lead_days.setVisible(False)

    def _view_mode(self, mode: str, *, emit: bool = True) -> None:
        self._mode = mode if mode in self.MODES else "follow"
        self._mode_stack.setCurrentWidget(self._mode_pages[self._mode])
        self._refresh_deadline_copy()
        self._refresh_selection_visuals()
        self.updateGeometry()
        if emit:
            self.changed.emit()

    def _set_mode(self, mode: str, *, emit: bool = True) -> None:
        """Programmatic compatibility setter: view and select one mode."""
        mode = mode if mode in self.MODES else "follow"
        self._selected_mode = mode
        self._view_mode(mode, emit=False)
        self._refresh_selection_visuals()
        if emit:
            self.changed.emit()

    def _select_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            return
        if mode == "follow" and not self.mode_buttons["follow"].isEnabled():
            self._refresh_selection_visuals()
            self._show_selection_notice("请先勾选事项时间，再选中“跟随事项时间”。")
            return
        if self._selected_mode == mode:
            self._selected_mode = None
            self._refresh_selection_visuals()
            self._show_selection_notice("已取消当前提醒方式的选中状态，请选择一种提醒方式。")
            if not self._loading:
                self.changed.emit()
            return
        if self._selected_mode is not None and self._selected_mode != mode:
            self._refresh_selection_visuals()
            self._show_selection_notice(
                f"提醒方式已经被选中了：{self.MODE_LABELS[self._selected_mode]}。请先取消当前选中。"
            )
            return
        self._selected_mode = mode
        self._view_mode(mode, emit=False)
        self._refresh_selection_visuals()
        self._hide_selection_notice()
        if not self._loading:
            self.changed.emit()

    def selected_mode(self) -> str | None:
        return self._selected_mode

    def has_selection(self) -> bool:
        return self._selected_mode in self.MODES

    def clear_selection(self) -> None:
        """Clear the active mode while retaining each mode's editable draft."""
        self._selected_mode = None
        self._view_mode("follow", emit=False)
        self._refresh_selection_visuals()
        self._hide_selection_notice()

    def _show_selection_notice(self, text: str) -> None:
        self.selection_notice.setText(text)
        self.selection_notice.setVisible(False)
        QToolTip.showText(
            self.selection_button.mapToGlobal(self.selection_button.rect().bottomLeft()),
            text,
            self.selection_button,
            self.selection_button.rect(),
            3500,
        )
        QTimer.singleShot(3500, self._hide_selection_notice)

    def _hide_selection_notice(self) -> None:
        self.selection_notice.clear()
        self.selection_notice.setVisible(False)

    def _refresh_selection_visuals(self) -> None:
        selected = self._selected_mode
        for mode in self.MODES:
            is_selected = selected is None or mode == selected
            card = self.mode_cards[mode]
            card.setProperty("selected", mode == selected)
            if selected is not None and not is_selected:
                # Qt owns and may delete a graphics effect when it is removed
                # from a widget, so always create a fresh effect here instead
                # of retaining a potentially stale wrapped C++ object.
                effect = QGraphicsOpacityEffect(card)
                effect.setOpacity(0.48)
                card.setGraphicsEffect(effect)
                panel_effect = QGraphicsOpacityEffect(self._mode_panels[mode])
                panel_effect.setOpacity(0.48)
                self._mode_panels[mode].setGraphicsEffect(panel_effect)
            else:
                card.setGraphicsEffect(None)
                self._mode_panels[mode].setGraphicsEffect(None)
            card.style().unpolish(card)
            card.style().polish(card)
        current_selected = selected == self._mode
        self.selection_button.blockSignals(True)
        self.selection_button.setChecked(current_selected)
        self.selection_button.setText("已选中" if current_selected else "选中")
        self.selection_button.blockSignals(False)
        if self._mode == "follow" and not self.mode_buttons["follow"].isEnabled():
            self.selection_button.setEnabled(False)
        else:
            self.selection_button.setEnabled(True)
        self.updateGeometry()

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

    def _capture_drafts(self) -> dict[str, dict]:
        """Capture all three editable plans, including plans not selected."""
        self._drafts = {
            "follow": {
                "important_reminder_offset_minutes": int(self._offset_minutes),
            },
            "deadline": {
                "important_reminder_target_date": self.deadline_target.date().toString("yyyy-MM-dd"),
                "important_reminder_time": f"{self.deadline_hour.currentData():02d}:{self.deadline_minute.currentData():02d}",
                "important_reminder_lead_days": int(self.lead_days.currentData() or 0),
            },
            "weekly": {
                "important_reminder_start_date": self.weekly_start.date().toString("yyyy-MM-dd"),
                "important_reminder_time": f"{self.weekly_hour.currentData():02d}:{self.weekly_minute.currentData():02d}",
                "important_reminder_weekday": int(self.weekday.currentData() or 1),
                "important_reminder_repeat_unit": self._repeat_values()[0],
                "important_reminder_repeat_interval": self._repeat_values()[1],
            },
        }
        return self._drafts

    @staticmethod
    def _parse_drafts(raw) -> dict[str, dict]:
        if not raw:
            return {mode: {} for mode in ImportantReminderSchedule.MODES}
        try:
            parsed = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            return {mode: {} for mode in ImportantReminderSchedule.MODES}
        if not isinstance(parsed, dict):
            return {mode: {} for mode in ImportantReminderSchedule.MODES}
        return {
            mode: dict(parsed.get(mode, {})) if isinstance(parsed.get(mode, {}), dict) else {}
            for mode in ImportantReminderSchedule.MODES
        }

    def _apply_draft(self, mode: str, draft: dict) -> None:
        """Apply one stored draft while loading, without emitting changes."""
        if mode == "follow":
            offset = int(draft.get("important_reminder_offset_minutes", 0) or 0)
            if offset in self.offset_buttons:
                self._set_offset(offset, emit=False)
            else:
                index = self.custom_offset.findData(offset)
                self.custom_offset.setCurrentIndex(max(1, index))
            return
        if mode == "deadline":
            target = draft.get("important_reminder_target_date")
            if target:
                self.deadline_target.setDate(QDate.fromString(str(target), "yyyy-MM-dd"))
            lead = int(draft.get("important_reminder_lead_days", 0) or 0)
            self.lead_days.setCurrentIndex(max(0, self.lead_days.findData(lead)))
            reminder_time = draft.get("important_reminder_time")
            combos = ((self.deadline_hour, self.deadline_minute),)
        else:
            start = draft.get("important_reminder_start_date")
            if start:
                self.weekly_start.setDate(QDate.fromString(str(start), "yyyy-MM-dd"))
            self.weekday.setCurrentIndex(max(0, self.weekday.findData(int(draft.get("important_reminder_weekday", 1) or 1))))
            unit = str(draft.get("important_reminder_repeat_unit", "week") or "week")
            interval = max(1, int(draft.get("important_reminder_repeat_interval", 1) or 1))
            preset_index = self._repeat_preset_index(unit, interval)
            if preset_index >= 0:
                self.repeat_frequency.setCurrentIndex(preset_index)
            else:
                self.repeat_frequency.setCurrentIndex(self._repeat_preset_index("custom", 0))
                self.repeat_unit.setCurrentIndex(max(0, self.repeat_unit.findData(unit)))
                self.repeat_interval.setValue(interval)
            reminder_time = draft.get("important_reminder_time")
            combos = ((self.weekly_hour, self.weekly_minute),)
        if reminder_time:
            try:
                hour, minute = str(reminder_time).split(":", 1)
                for combo, value in ((combos[0][0], int(hour)), (combos[0][1], int(minute))):
                    combo.setCurrentIndex(max(0, combo.findData(value)))
            except (TypeError, ValueError):
                pass

    def load(self, task) -> None:
        self._loading = True
        supports_enabled = "windows_reminder_enabled" not in task.keys() or bool(task["windows_reminder_enabled"])
        has_stored_mode = "important_reminder_mode" in task.keys()
        stored_mode = str(task["important_reminder_mode"]) if has_stored_mode else "follow"
        if stored_mode not in self.MODES:
            stored_mode = "follow"
        self._selected_mode = stored_mode if supports_enabled and has_stored_mode else None
        self._drafts = self._parse_drafts(task["important_reminder_drafts"] if "important_reminder_drafts" in task.keys() else None)
        self.set_task_date(QDate.fromString(task["task_date"], "yyyy-MM-dd"))
        target = task["important_reminder_target_date"] if "important_reminder_target_date" in task.keys() else None
        self._deadline_target_explicit = bool(target)
        self.deadline_target.setDate(QDate.fromString(str(target or task["task_date"]), "yyyy-MM-dd"))
        legacy_values = {
            "follow": {
                "important_reminder_offset_minutes": int(task["important_reminder_offset_minutes"] or 0) if "important_reminder_offset_minutes" in task.keys() else 0,
            },
            "deadline": {
                "important_reminder_target_date": target or task["task_date"],
                "important_reminder_time": task["important_reminder_time"] if "important_reminder_time" in task.keys() else None,
                "important_reminder_lead_days": int(task["important_reminder_lead_days"] or 0) if "important_reminder_lead_days" in task.keys() else 0,
            },
            "weekly": {
                "important_reminder_start_date": task["important_reminder_start_date"] if "important_reminder_start_date" in task.keys() else task["task_date"],
                "important_reminder_time": task["important_reminder_time"] if "important_reminder_time" in task.keys() else None,
                "important_reminder_weekday": int(task["important_reminder_weekday"] or 1) if "important_reminder_weekday" in task.keys() else 1,
                "important_reminder_repeat_unit": str(task["important_reminder_repeat_unit"] or "week") if "important_reminder_repeat_unit" in task.keys() else "week",
                "important_reminder_repeat_interval": max(1, int(task["important_reminder_repeat_interval"] or 1)) if "important_reminder_repeat_interval" in task.keys() else 1,
            },
        }
        for mode in self.MODES:
            draft = dict(legacy_values[mode]) if mode == stored_mode else {}
            draft.update(self._drafts.get(mode, {}))
            self._apply_draft(mode, draft)
        self._deadline_target_explicit = bool(self._drafts.get("deadline", {}).get("important_reminder_target_date") or target)
        self._view_mode(stored_mode if self._selected_mode else "follow", emit=False)
        self._loading = False
        self._refresh_deadline_copy()
        self._on_repeat_frequency_changed(emit=False)
        self._refresh_selection_visuals()

    def values(self) -> dict:
        drafts = self._capture_drafts()
        # Only the explicitly selected mode is active. Unselected mode panels
        # remain editable as drafts but cannot become effective accidentally.
        mode = self._selected_mode or "follow"
        if mode == "follow":
            reminder_time = None
            start_date = None
            target_date = None
            weekday = None
            lead_days = 0
        elif mode == "deadline":
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
        if mode != "weekly":
            repeat_unit, repeat_interval = "week", 1
        return {
            "important_reminder_mode": mode,
            "important_reminder_offset_minutes": self._offset_minutes if mode == "follow" else 0,
            "important_reminder_start_date": start_date,
            "important_reminder_target_date": target_date,
            "important_reminder_time": reminder_time,
            "important_reminder_lead_days": lead_days,
            "important_reminder_weekday": weekday,
            "important_reminder_repeat_unit": repeat_unit,
            "important_reminder_repeat_interval": repeat_interval,
            "important_reminder_at": None,
            "important_reminder_drafts": json.dumps(drafts, ensure_ascii=False, sort_keys=True),
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
        margins = layout.contentsMargins()
        self.setMinimumWidth(max(600, self.schedule.sizeHint().width() + margins.left() + margins.right() + 8))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("完成提醒设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Measure the largest editor page once (the custom weekly row is the
        # tallest state), then keep the dialog height fixed while the user
        # switches modes. This prevents the native window from re-centering
        # and makes the three mode buttons stay on one horizontal axis.
        stable_mode = self.schedule._mode
        was_custom_repeat = (self.schedule.repeat_frequency.currentData() or ("", 0))[0] == "custom"
        normal_schedule_height = self.schedule.sizeHint().height()
        normal_stack_height = self.schedule._mode_stack.sizeHint().height()
        stable_frequency_index = self.schedule.repeat_frequency.currentIndex()
        stable_repeat_unit_index = self.schedule.repeat_unit.currentIndex()
        stable_repeat_interval = self.schedule.repeat_interval.value()
        self.schedule._mode_stack.setCurrentWidget(self.schedule._mode_pages["weekly"])
        self.schedule.repeat_frequency.blockSignals(True)
        self.schedule.repeat_frequency.setCurrentIndex(self.schedule._repeat_preset_index("custom", 0))
        self.schedule.repeat_frequency.blockSignals(False)
        self.schedule._on_repeat_frequency_changed(emit=False)
        expanded_stack_height = self.schedule._mode_stack.sizeHint().height()
        stable_schedule_height = normal_schedule_height + max(0, expanded_stack_height - normal_stack_height)
        self.schedule.setFixedHeight(stable_schedule_height)
        self.adjustSize()
        stable_height = self.height()
        self.schedule.repeat_frequency.blockSignals(True)
        self.schedule.repeat_frequency.setCurrentIndex(stable_frequency_index)
        self.schedule.repeat_unit.setCurrentIndex(stable_repeat_unit_index)
        self.schedule.repeat_interval.setValue(stable_repeat_interval)
        self.schedule.repeat_frequency.blockSignals(False)
        self.schedule._mode_stack.setCurrentWidget(self.schedule._mode_pages[stable_mode])
        self.schedule._on_repeat_frequency_changed(emit=False)
        self._normal_schedule_height = normal_schedule_height
        self._expanded_schedule_height = stable_schedule_height
        self.schedule.setFixedHeight(
            stable_schedule_height if was_custom_repeat else normal_schedule_height
        )
        self.schedule.changed.connect(self._sync_schedule_height)
        self.setFixedHeight(stable_height)

    def _accept_settings(self) -> None:
        if not self.schedule.has_selection():
            self.schedule._show_selection_notice("请先点击右侧的“选中”。")
            return
        self.accept()

    def _sync_schedule_height(self) -> None:
        """Allow the custom weekly row to expand inside the fixed dialog."""
        expanded = (self.schedule.repeat_frequency.currentData() or ("", 0))[0] == "custom"
        self.schedule.setFixedHeight(
            self._expanded_schedule_height if expanded else self._normal_schedule_height
        )

    def values(self) -> dict:
        return self.schedule.values()
