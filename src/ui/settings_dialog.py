"""V2 settings dialog with compact section cards and horizontal rows."""

from __future__ import annotations

import json
from datetime import datetime

from PyQt6.QtCore import QSignalBlocker, QTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ui.controls import NoWheelComboBox, NoWheelTimeEdit, StepCounter, TIME_HOURS, TIME_MINUTES
from ui.theme import SETTINGS_STYLE


class GuidedTimeCombo(QPushButton):
    """One compact slot that drops down the same hour/minute controls as a task."""

    valueChanged = pyqtSignal(str)
    HOURS = TIME_HOURS
    MINUTES = TIME_MINUTES

    def __init__(self, value: str = "", parent=None) -> None:
        super().__init__(parent)
        self._value = value if self._valid_value(value) else ""
        self.setObjectName("timeSlotButton")
        self.setText(self._value or "无")
        self.setMinimumWidth(78)
        self.setProperty("selected", bool(self._value))
        self.clicked.connect(self._open_picker)

    @classmethod
    def _valid_value(cls, value: str) -> bool:
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except (AttributeError, ValueError):
            return False
        return hour in cls.HOURS and minute in cls.MINUTES

    @classmethod
    def guided_default(cls) -> tuple[int, int]:
        return min(22, max(7, datetime.now().hour + 1)), 0

    def currentData(self) -> str:  # noqa: N802
        return self._value

    def set_value(self, value: str) -> None:
        value = value if self._valid_value(value) else ""
        changed = value != self._value
        self._value = value
        self.setText(value or "无")
        self.setProperty("selected", bool(value))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        if changed:
            self.valueChanged.emit(value)

    def _open_picker(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(SETTINGS_STYLE)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        no_time = QCheckBox("无")
        no_time.setChecked(not bool(self._value))
        layout.addWidget(no_time)
        time_row = QHBoxLayout()
        hour_combo = NoWheelComboBox()
        for hour in self.HOURS:
            hour_combo.addItem(f"{hour:02d} 时", hour)
        minute_combo = NoWheelComboBox()
        for minute in self.MINUTES:
            minute_combo.addItem(f"{minute:02d} 分", minute)
        if self._value:
            hour, minute = (int(part) for part in self._value.split(":"))
        else:
            hour, minute = self.guided_default()
        hour_combo.setCurrentIndex(hour_combo.findData(hour))
        minute_combo.setCurrentIndex(minute_combo.findData(minute))
        time_row.addWidget(hour_combo)
        time_row.addWidget(minute_combo)
        layout.addLayout(time_row)
        # The selectors stay usable while "无" is checked. Choosing either
        # selector is an explicit time-setting action, so "无" is cleared.
        hour_combo.activated.connect(lambda _: no_time.setChecked(False))
        minute_combo.activated.connect(lambda _: no_time.setChecked(False))
        actions = QHBoxLayout()
        cancel = QPushButton("取消")
        confirm = QPushButton("确定")
        confirm.setObjectName("primaryButton")
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        cancel.clicked.connect(menu.close)

        def apply_value() -> None:
            if no_time.isChecked():
                self.set_value("")
            else:
                self.set_value(f"{hour_combo.currentData():02d}:{minute_combo.currentData():02d}")
            menu.close()

        confirm.clicked.connect(apply_value)
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))


class MultilineComboBox(NoWheelComboBox):
    """A compact combo whose selected encouragement can visibly use two lines."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(48)
        self.setMinimumWidth(210)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)

    def paintEvent(self, event):  # noqa: N802
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        text = option.currentText
        option.currentText = ""
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        edit_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        ).adjusted(4, 2, -2, -2)
        painter.drawText(
            edit_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
            text,
        )


class AutoHeightTextEdit(QPlainTextEdit):
    """A fixed-height editor that accepts up to three intentional lines."""

    MAX_LINES = 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(76)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._trimming_lines = False
        self.textChanged.connect(self._limit_to_three_lines)

    def _limit_to_three_lines(self) -> None:
        if self._trimming_lines:
            return
        text = self.toPlainText()
        # Newlines are deliberate wording choices for the float.  The former
        # visual-wrap measurement accidentally rejected ordinary Enter input;
        # only a fourth explicit line should be removed.
        candidate = "\n".join(text.split("\n")[:self.MAX_LINES])
        if candidate == text:
            return
        self._trimming_lines = True
        self.setPlainText(candidate)
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self._trimming_lines = False

class SettingsSection(QFrame):
    def __init__(self, title: str, parent=None, *, inline_heading: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("settingsSection")
        outer = QVBoxLayout(self)
        # Five compact time chips are the widest ordinary settings row.  Keep
        # the card generous vertically but trim its side padding so the dialog
        # stays narrow without creating a horizontal scroll bar.
        outer.setContentsMargins(12, 14, 12, 16)
        outer.setSpacing(9)
        self.heading = QLabel(title)
        self.heading.setObjectName("sectionTitle")
        self.heading_row = QHBoxLayout() if inline_heading else None
        if self.heading_row is None:
            outer.addWidget(self.heading)
        else:
            self.heading_row.setContentsMargins(0, 0, 0, 0)
            self.heading_row.setSpacing(9)
            self.heading_row.addWidget(self.heading)
            outer.addLayout(self.heading_row)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        outer.addLayout(self.rows)

    def add_row(self, row: QHBoxLayout, *, divider: bool = False) -> None:
        if divider:
            line = QFrame()
            line.setObjectName("rowDivider")
            line.setFixedHeight(1)
            self.rows.addWidget(line)
        self.rows.addLayout(row)

    def add_to_heading(self, *widgets: QWidget) -> None:
        """Append compact controls beside an inline section heading."""
        if self.heading_row is None:
            raise RuntimeError("This settings section does not have an inline heading")
        for widget in widgets:
            self.heading_row.addWidget(widget)
        self.heading_row.addStretch(1)


class SettingsDialog(QDialog):
    OFFWORK_CHOICES = (5, 10, 15, 20, 30)
    FIXED_WATER_TIMES = ("10:15", "15:15")
    FIXED_EYE_TIMES = ("11:35", "16:40")
    MEAL_TIMES = ("11:59", "17:59")
    # Match meal chips exactly: a time never gets more horizontal room merely
    # because it contains a colon and four digits.
    WATER_SLOT_SIZE = (54, 31)
    GREETING_EDITOR_SIZE = (230, 76)

    def __init__(self, db, greetings: list[str], parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setObjectName("settingsDialog")
        self.setWindowTitle("设置")
        self.resize(560, 720)
        self.setMinimumSize(550, 580)
        self.setStyleSheet(SETTINGS_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.sections = QVBoxLayout(host)
        self.sections.setContentsMargins(5, 5, 5, 5)
        self.sections.setSpacing(12)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self._build_work_section()
        self._build_reminder_section()
        self._build_greeting_section(greetings)
        self._build_float_section()
        self._build_fixed_text_section()
        self.sections.addStretch(1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self._initial_state = self._comparison_state()

    @staticmethod
    def _row_label(text: str, width: int = 112) -> QLabel:
        label = QLabel(text)
        label.setObjectName("rowLabel")
        # Fixed labels keep the custom-greeting editor aligned with the row
        # above instead of allowing a longer label to push it to the right.
        label.setFixedWidth(width)
        return label

    @staticmethod
    def _row(*widgets, stretch: bool = True) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        for widget in widgets:
            row.addWidget(widget)
        if stretch:
            row.addStretch(1)
        return row

    @staticmethod
    def _load_json_list(raw: str, default: list[str]) -> list[str]:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return list(default)
        return [str(item) for item in value] if isinstance(value, list) else list(default)

    @staticmethod
    def _choice(text: str, checked: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("choiceChip")
        button.setCheckable(True)
        button.setChecked(checked)
        return button

    def _time_slot_column(self, widget: QWidget, egg_text: str = "") -> QWidget:
        width, height = self.WATER_SLOT_SIZE
        widget.setFixedSize(width, height)
        column = QWidget()
        column.setFixedWidth(width)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(1)
        egg = QLabel(egg_text or " ")
        egg.setObjectName("easterEgg")
        egg.setFixedHeight(11)
        egg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column_layout.addWidget(egg)
        column_layout.addWidget(widget)
        return column

    def _build_work_section(self) -> None:
        section = SettingsSection("工作与启动", inline_heading=True)
        self.end_time = NoWheelTimeEdit()
        self.end_time.setDisplayFormat("HH:mm")
        self.end_time.setTime(QTime.fromString(self.db.get_setting("off_work_time", "18:10"), "HH:mm"))
        self.end_time.setFixedWidth(92)
        self.autostart = QCheckBox("开机自动启动")
        self.autostart.setChecked(self.db.get_setting("autostart", "1") == "1")
        section.add_to_heading(self._row_label("下班时间", 58), self.end_time, self.autostart)
        self.sections.addWidget(section)

    def _build_reminder_section(self) -> None:
        section = SettingsSection("提醒")

        self.water_enabled = QCheckBox("喝水提醒")
        self.water_enabled.setMinimumWidth(92)
        self.water_enabled.setChecked(self.db.get_setting("water_enabled", "1") == "1")
        selected_fixed = set(self._load_json_list(
            self.db.get_setting("water_fixed_times", ""), list(self.FIXED_WATER_TIMES)
        ))
        self.water_fixed_buttons = []
        fixed_water = []
        for value in self.FIXED_WATER_TIMES:
            button = self._choice(value, value in selected_fixed)
            self.water_fixed_buttons.append(button)
            fixed_water.append(self._time_slot_column(button, "饮茶时间！" if value == "15:15" else ""))
        custom_values = self._load_json_list(self.db.get_setting("water_custom_times", ""), ["", "", ""])
        custom_values = (custom_values + ["", "", ""])[:3]
        self.water_custom = [GuidedTimeCombo(value) for value in custom_values]
        for combo in self.water_custom:
            combo.valueChanged.connect(
                lambda _, changed=combo: self._prevent_duplicate_time(
                    changed, self.FIXED_WATER_TIMES, self.water_custom, "喝水提醒"
                )
            )
        custom_water = [self._time_slot_column(combo) for combo in self.water_custom]
        water_row = self._row(self.water_enabled, *fixed_water, *custom_water)
        section.add_row(water_row)

        self.eye_enabled = QCheckBox("用眼提醒")
        self.eye_enabled.setMinimumWidth(92)
        self.eye_enabled.setChecked(self.db.get_setting("eye_enabled", "1") == "1")
        selected_eye = set(self._load_json_list(
            self.db.get_setting("eye_fixed_times", ""), list(self.FIXED_EYE_TIMES)
        ))
        self.eye_fixed_buttons = []
        fixed_eye = []
        for value in self.FIXED_EYE_TIMES:
            button = self._choice(value, value in selected_eye)
            self.eye_fixed_buttons.append(button)
            # Unlike water, the eye row has no small themed caption above a
            # chip.  Giving it an empty caption created a visibly taller row.
            button.setFixedSize(*self.WATER_SLOT_SIZE)
            fixed_eye.append(button)
        eye_custom_values = self._load_json_list(self.db.get_setting("eye_custom_times", ""), ["", "", ""])
        eye_custom_values = (eye_custom_values + ["", "", ""])[:3]
        self.eye_custom = [GuidedTimeCombo(value) for value in eye_custom_values]
        for combo in self.eye_custom:
            combo.valueChanged.connect(
                lambda _, changed=combo: self._prevent_duplicate_time(
                    changed, self.FIXED_EYE_TIMES, self.eye_custom, "用眼提醒"
                )
            )
        for combo in self.eye_custom:
            combo.setFixedSize(*self.WATER_SLOT_SIZE)
        custom_eye = list(self.eye_custom)
        section.add_row(self._row(self.eye_enabled, *fixed_eye, *custom_eye), divider=True)

        self.meal_enabled = QCheckBox("吃饭提醒")
        self.meal_enabled.setMinimumWidth(112)
        self.meal_enabled.setChecked(self.db.get_setting("meal_enabled", "0") == "1")
        selected_meals = set(self._load_json_list(self.db.get_setting("meal_times", ""), list(self.MEAL_TIMES)))
        self.meal_buttons = [self._choice(value, value in selected_meals) for value in self.MEAL_TIMES]
        for button in self.meal_buttons:
            button.setFixedSize(*self.WATER_SLOT_SIZE)
        section.add_row(self._row(self.meal_enabled, *self.meal_buttons), divider=True)

        self.offwork_enabled = QCheckBox("下班提醒")
        self.offwork_enabled.setMinimumWidth(112)
        self.offwork_enabled.setChecked(self.db.get_setting("offwork_enabled", "0") == "1")
        old_lead = self.db.get_setting("offwork_lead_minutes", "5")
        selected_leads = set(self._load_json_list(
            self.db.get_setting("offwork_lead_minutes_list", ""), [old_lead]
        ))
        self.offwork_buttons = [self._choice(f"{value}分钟", str(value) in selected_leads) for value in self.OFFWORK_CHOICES]
        for button in self.offwork_buttons:
            # A reminder lead has four full glyphs (for example “30分钟”).
            # It needs a little more room than a compact HH:MM time chip.
            button.setFixedSize(58, self.WATER_SLOT_SIZE[1])
            button.toggled.connect(lambda checked, changed=button: self._limit_offwork_choices(changed, checked))
        hint = QLabel("最多选2个")
        hint.setObjectName("hintLabel")
        hint.setFixedWidth(44)
        offwork_row = self._row(self.offwork_enabled, *self.offwork_buttons, hint)
        offwork_row.setSpacing(5)
        section.add_row(offwork_row, divider=True)

        self.overtime_enabled = QCheckBox("加班提醒")
        self.overtime_enabled.setMinimumWidth(112)
        self.overtime_enabled.setChecked(self.db.get_setting("overtime_enabled", "1") == "1")
        cadence_label = QLabel("频率")
        cadence_label.setObjectName("rowLabel")
        self.overtime_cadence = NoWheelComboBox()
        self.overtime_cadence.addItem("每半小时", "30")
        self.overtime_cadence.addItem("每1小时", "60")
        cadence = self.db.get_setting("overtime_cadence", "30")
        self.overtime_cadence.setCurrentIndex(max(0, self.overtime_cadence.findData(cadence)))
        self.overtime_cadence.setMinimumWidth(150)
        section.add_row(self._row(self.overtime_enabled, cadence_label, self.overtime_cadence), divider=True)
        self.sections.addWidget(section)

    def _build_greeting_section(self, greetings: list[str]) -> None:
        section = SettingsSection("顶部鼓励语")
        self.greeting = MultilineComboBox()
        self.greeting.setFixedSize(*self.GREETING_EDITOR_SIZE)
        self.greeting.addItems(greetings)
        saved = self.db.get_setting("float_greeting", greetings[0] if greetings else "")
        index = self.greeting.findText(saved)
        self.greeting.setCurrentIndex(index if index >= 0 else (0 if greetings else -1))
        self.delete_greeting = QPushButton("删除当前鼓励语")
        self.delete_greeting.setObjectName("dangerButton")
        self.delete_greeting.setFixedWidth(118)
        self.delete_greeting.clicked.connect(self._remove_greeting)
        section.add_row(self._row(self._row_label("当前鼓励语"), self.greeting, self.delete_greeting, stretch=False))

        self.custom_greeting = AutoHeightTextEdit()
        self.custom_greeting.setFixedSize(*self.GREETING_EDITOR_SIZE)
        self.custom_greeting.setPlaceholderText("可以输入多行鼓励语\n换行会原样显示在浮窗中")
        self.save_greeting = QPushButton("保存为新鼓励语")
        self.save_greeting.setFixedWidth(118)
        self.save_greeting.clicked.connect(self._save_custom_greeting)
        # The divider row has a tiny style margin of its own.  A 112px label
        # compensates for it so the editable box begins at exactly the same
        # left edge as the selected encouragement above.
        section.add_row(self._row(self._row_label("自定义鼓励语", 112), self.custom_greeting, self.save_greeting, stretch=False), divider=True)
        self.sections.addWidget(section)

    def _build_float_section(self) -> None:
        section = SettingsSection("浮窗显示数量调节")
        self.countdown_count = StepCounter()
        self.countdown_count.setRange(3, 5)
        self.countdown_count.setValue(int(self.db.get_setting("countdown_float_count", "3")))
        self.manual_count = StepCounter()
        self.manual_count.setRange(0, 4)
        self.manual_count.setValue(int(self.db.get_setting("manual_float_count", "3")))
        section.add_row(self._row(self._row_label("倒计时待办数量", 150), self.countdown_count))
        section.add_row(self._row(self._row_label("手动固定浮窗位数量", 150), self.manual_count), divider=True)
        self.collapse_delay = NoWheelComboBox()
        self.collapse_delay.addItem("4 秒（默认）", "4")
        self.collapse_delay.addItem("10 秒", "10")
        self.collapse_delay.addItem("仅手动收起", "manual")
        saved_delay = self.db.get_setting("float_auto_collapse", "4")
        self.collapse_delay.setCurrentIndex(max(0, self.collapse_delay.findData(saved_delay)))
        self.collapse_delay.setMinimumWidth(180)
        section.add_row(self._row(self._row_label("浮窗自动收起", 150), self.collapse_delay), divider=True)
        self.shortcut = NoWheelComboBox()
        self.shortcut.addItem("无快捷键", "none")
        self.shortcut.addItem("Alt + E（建议）", "alt+e")
        current = self.db.get_setting("float_shortcut", "none")
        self.shortcut.setCurrentIndex(max(0, self.shortcut.findData(current)))
        self.shortcut.setMinimumWidth(180)
        section.add_row(self._row(self._row_label("弹出快捷键", 150), self.shortcut), divider=True)
        self.sections.addWidget(section)

    def _build_fixed_text_section(self) -> None:
        section = SettingsSection("桌边重点位")
        hint = QLabel(
            "桌边重点位不是第二份待办清单，而是留给此刻最要紧事情的几个位置。\n"
            "重点事项完成后自动腾出；空位时显示下方的提示语。"
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        section.rows.addWidget(hint)
        self.fixed_texts: list[tuple[int, QLineEdit]] = []
        for slot in range(1, 4):
            edit = QLineEdit(self.db.get_setting(f"float_text_{slot}", ""))
            edit.setPlaceholderText("空位时显示的提示语")
            self.fixed_texts.append((slot, edit))
            section.add_row(
                self._row(self._row_label(f"重点位 {slot} 提示语", 130), edit, stretch=False),
                divider=slot > 1,
            )
        self.sections.addWidget(section)

    def _limit_offwork_choices(self, changed: QPushButton, checked: bool) -> None:
        if checked and sum(button.isChecked() for button in self.offwork_buttons) > 2:
            with QSignalBlocker(changed):
                changed.setChecked(False)
            QMessageBox.information(self, "下班提醒", "下班提醒时间最多选2个。")

    def _prevent_duplicate_time(
        self,
        changed: GuidedTimeCombo,
        fixed_times: tuple[str, ...],
        custom_times: list[GuidedTimeCombo],
        reminder_name: str,
    ) -> None:
        value = changed.currentData()
        if not value:
            return
        selected = [combo.currentData() for combo in custom_times if combo is not changed]
        if value in fixed_times or value in selected:
            with QSignalBlocker(changed):
                changed.set_value("")
            QMessageBox.information(self, reminder_name, "这个时间已经存在，请选择其他时间。")

    def _remove_greeting(self) -> None:
        index = self.greeting.currentIndex()
        if index >= 0:
            self.greeting.removeItem(index)

    def _save_custom_greeting(self) -> None:
        text = self.custom_greeting.toPlainText().strip()
        if not text:
            return
        index = self.greeting.findText(text)
        if index < 0:
            self.greeting.addItem(text)
            index = self.greeting.count() - 1
        self.greeting.setCurrentIndex(index)
        self.custom_greeting.clear()

    def values(self) -> dict:
        greetings = [
            self.greeting.itemText(index).strip()
            for index in range(self.greeting.count())
            if self.greeting.itemText(index).strip()
        ]
        current_greeting = self.greeting.currentText().strip() if self.greeting.currentIndex() >= 0 else ""
        return {
            "off_work_time": self.end_time.time().toString("HH:mm"),
            "autostart": self.autostart.isChecked(),
            "water_enabled": self.water_enabled.isChecked(),
            "water_fixed_times": [
                value for value, button in zip(self.FIXED_WATER_TIMES, self.water_fixed_buttons)
                if button.isChecked()
            ],
            "water_custom_times": [combo.currentData() or "" for combo in self.water_custom],
            "eye_enabled": self.eye_enabled.isChecked(),
            "eye_fixed_times": [
                value for value, button in zip(self.FIXED_EYE_TIMES, self.eye_fixed_buttons)
                if button.isChecked()
            ],
            "eye_custom_times": [combo.currentData() or "" for combo in self.eye_custom],
            "meal_enabled": self.meal_enabled.isChecked(),
            "meal_times": [value for value, button in zip(self.MEAL_TIMES, self.meal_buttons) if button.isChecked()],
            "offwork_enabled": self.offwork_enabled.isChecked(),
            "offwork_leads": [
                value for value, button in zip(self.OFFWORK_CHOICES, self.offwork_buttons) if button.isChecked()
            ],
            "overtime_enabled": self.overtime_enabled.isChecked(),
            "overtime_cadence": self.overtime_cadence.currentData(),
            "greetings": greetings,
            "greeting": current_greeting,
            "countdown_count": self.countdown_count.value(),
            "manual_count": self.manual_count.value(),
            "collapse_delay": self.collapse_delay.currentData(),
            "shortcut": self.shortcut.currentData(),
            "fixed_texts": {slot: edit.text().strip() for slot, edit in self.fixed_texts},
        }

    def _comparison_state(self) -> str:
        state = self.values()
        state["custom_greeting_draft"] = self.custom_greeting.toPlainText()
        return json.dumps(state, ensure_ascii=False, sort_keys=True)

    def accept(self) -> None:
        # A typed custom greeting is part of the settings form. Saving the form
        # must not silently discard it just because its adjacent button was not
        # clicked first.
        if self.custom_greeting.toPlainText().strip():
            self._save_custom_greeting()
        super().accept()

    def reject(self) -> None:
        if not hasattr(self, "_initial_state") or self._comparison_state() == self._initial_state:
            super().reject()
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle("设置尚未保存")
        prompt.setText("设置没有保存，是否立即保存？")
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        prompt.button(QMessageBox.StandardButton.Save).setText("立即保存")
        prompt.button(QMessageBox.StandardButton.Discard).setText("不保存")
        prompt.button(QMessageBox.StandardButton.Cancel).setText("返回设置")
        prompt.setDefaultButton(QMessageBox.StandardButton.Cancel)
        result = prompt.exec()
        if result == QMessageBox.StandardButton.Save:
            self.accept()
        elif result == QMessageBox.StandardButton.Discard:
            QDialog.reject(self)
