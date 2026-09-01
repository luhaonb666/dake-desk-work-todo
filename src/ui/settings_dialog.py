"""V2 settings dialog with compact section cards and horizontal rows."""

from __future__ import annotations

import json
from datetime import datetime

from PyQt6.QtCore import QSignalBlocker, QTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ui.theme import SETTINGS_STYLE


class GuidedTimeCombo(QPushButton):
    """One compact slot that drops down the same hour/minute controls as a task."""

    valueChanged = pyqtSignal(str)
    HOURS = tuple(range(7, 23))
    MINUTES = tuple(range(0, 60, 10))

    def __init__(self, value: str = "", parent=None) -> None:
        super().__init__(parent)
        self._value = value if self._valid_value(value) else ""
        self.setObjectName("timeSlotButton")
        self.setText(self._value or "无")
        self.setMinimumWidth(78)
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
        if value == self._value:
            return
        self._value = value
        self.setText(value or "无")
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
        hour_combo = QComboBox()
        for hour in self.HOURS:
            hour_combo.addItem(f"{hour:02d} 时", hour)
        minute_combo = QComboBox()
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
        no_time.toggled.connect(lambda checked: (hour_combo.setDisabled(checked), minute_combo.setDisabled(checked)))
        hour_combo.setDisabled(no_time.isChecked())
        minute_combo.setDisabled(no_time.isChecked())
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


class AutoHeightTextEdit(QPlainTextEdit):
    """Small multiline editor that grows as intentional line breaks are added."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(58)
        self.setMaximumHeight(116)
        self.document().blockCountChanged.connect(self._resize_to_lines)

    def _resize_to_lines(self) -> None:
        lines = max(2, self.document().blockCount())
        self.setFixedHeight(min(116, 24 + lines * 20))


class SettingsSection(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsSection")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        outer.addWidget(heading)
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


class SettingsDialog(QDialog):
    OFFWORK_CHOICES = (5, 10, 15, 20, 30)
    FIXED_WATER_TIMES = ("10:15", "15:15")
    MEAL_TIMES = ("11:59", "17:59")

    def __init__(self, db, greetings: list[str], parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setObjectName("settingsDialog")
        self.setWindowTitle("设置")
        self.resize(820, 720)
        self.setMinimumSize(680, 580)
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

    @staticmethod
    def _row_label(text: str, width: int = 112) -> QLabel:
        label = QLabel(text)
        label.setObjectName("rowLabel")
        label.setMinimumWidth(width)
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

    def _build_work_section(self) -> None:
        section = SettingsSection("工作与启动")
        self.end_time = QTimeEdit()
        self.end_time.setDisplayFormat("HH:mm")
        self.end_time.setTime(QTime.fromString(self.db.get_setting("off_work_time", "18:10"), "HH:mm"))
        self.end_time.setMinimumWidth(150)
        self.autostart = QCheckBox("开机自动启动")
        self.autostart.setChecked(self.db.get_setting("autostart", "1") == "1")
        section.add_row(self._row(self._row_label("下班时间"), self.end_time, self.autostart))
        self.sections.addWidget(section)

    def _build_reminder_section(self) -> None:
        section = SettingsSection("提醒")

        self.water_enabled = QCheckBox("喝水提醒")
        self.water_enabled.setMinimumWidth(112)
        self.water_enabled.setChecked(self.db.get_setting("water_enabled", "1") == "1")
        fixed_water = []
        for value in self.FIXED_WATER_TIMES:
            label = QLabel(value)
            label.setObjectName("fixedChip")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumWidth(56)
            fixed_water.append(label)
        custom_values = self._load_json_list(self.db.get_setting("water_custom_times", ""), ["", "", ""])
        custom_values = (custom_values + ["", "", ""])[:3]
        self.water_custom = [GuidedTimeCombo(value) for value in custom_values]
        for combo in self.water_custom:
            combo.valueChanged.connect(lambda _, changed=combo: self._prevent_duplicate_water(changed))
        water_row = self._row(self.water_enabled, *fixed_water, *self.water_custom)
        section.add_row(water_row)

        self.meal_enabled = QCheckBox("吃饭提醒")
        self.meal_enabled.setMinimumWidth(112)
        self.meal_enabled.setChecked(self.db.get_setting("meal_enabled", "0") == "1")
        selected_meals = set(self._load_json_list(self.db.get_setting("meal_times", ""), list(self.MEAL_TIMES)))
        self.meal_buttons = [self._choice(value, value in selected_meals) for value in self.MEAL_TIMES]
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
            button.toggled.connect(lambda checked, changed=button: self._limit_offwork_choices(changed, checked))
        hint = QLabel("最多选2个")
        hint.setObjectName("hintLabel")
        section.add_row(self._row(self.offwork_enabled, *self.offwork_buttons, hint), divider=True)

        self.overtime_enabled = QCheckBox("加班提醒")
        self.overtime_enabled.setMinimumWidth(112)
        self.overtime_enabled.setChecked(self.db.get_setting("overtime_enabled", "1") == "1")
        cadence_label = QLabel("频率")
        cadence_label.setObjectName("rowLabel")
        self.overtime_cadence = QComboBox()
        self.overtime_cadence.addItem("每半小时", "30")
        self.overtime_cadence.addItem("每1小时", "60")
        cadence = self.db.get_setting("overtime_cadence", "30")
        self.overtime_cadence.setCurrentIndex(max(0, self.overtime_cadence.findData(cadence)))
        self.overtime_cadence.setMinimumWidth(150)
        section.add_row(self._row(self.overtime_enabled, cadence_label, self.overtime_cadence), divider=True)
        self.sections.addWidget(section)

    def _build_greeting_section(self, greetings: list[str]) -> None:
        section = SettingsSection("顶部鼓励语")
        self.greeting = QComboBox()
        self.greeting.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.greeting.addItems(greetings)
        saved = self.db.get_setting("float_greeting", greetings[0] if greetings else "")
        index = self.greeting.findText(saved)
        self.greeting.setCurrentIndex(index if index >= 0 else (0 if greetings else -1))
        self.delete_greeting = QPushButton("删除当前鼓励语")
        self.delete_greeting.setObjectName("dangerButton")
        self.delete_greeting.clicked.connect(self._remove_greeting)
        section.add_row(self._row(self._row_label("当前鼓励语"), self.greeting, self.delete_greeting, stretch=False))

        self.custom_greeting = AutoHeightTextEdit()
        self.custom_greeting.setPlaceholderText("可以输入多行鼓励语，换行会原样显示在浮窗中")
        self.save_greeting = QPushButton("保存为新鼓励语")
        self.save_greeting.clicked.connect(self._save_custom_greeting)
        section.add_row(self._row(self._row_label("自定义鼓励语"), self.custom_greeting, self.save_greeting, stretch=False), divider=True)
        self.sections.addWidget(section)

    def _build_float_section(self) -> None:
        section = SettingsSection("浮窗显示数量调节")
        self.countdown_count = QSpinBox()
        self.countdown_count.setRange(3, 5)
        self.countdown_count.setValue(int(self.db.get_setting("countdown_float_count", "3")))
        self.countdown_count.setMinimumWidth(90)
        self.manual_count = QSpinBox()
        self.manual_count.setRange(0, 4)
        self.manual_count.setValue(int(self.db.get_setting("manual_float_count", "3")))
        self.manual_count.setMinimumWidth(90)
        section.add_row(self._row(self._row_label("倒计时待办数量", 150), self.countdown_count))
        section.add_row(self._row(self._row_label("手动固定浮窗位数量", 150), self.manual_count), divider=True)
        self.shortcut = QComboBox()
        self.shortcut.addItem("无快捷键", "none")
        self.shortcut.addItem("Alt + E（建议）", "alt+e")
        current = self.db.get_setting("float_shortcut", "none")
        self.shortcut.setCurrentIndex(max(0, self.shortcut.findData(current)))
        self.shortcut.setMinimumWidth(180)
        section.add_row(self._row(self._row_label("弹出快捷键", 150), self.shortcut), divider=True)
        self.sections.addWidget(section)

    def _build_fixed_text_section(self) -> None:
        section = SettingsSection("浮窗固定文字")
        self.fixed_texts: list[tuple[int, QLineEdit]] = []
        for slot in range(1, 4):
            edit = QLineEdit(self.db.get_setting(f"float_text_{slot}", ""))
            edit.setPlaceholderText("没有指定事项时显示的固定文字")
            self.fixed_texts.append((slot, edit))
            section.add_row(
                self._row(self._row_label(f"浮窗位置 {slot}", 112), edit, stretch=False),
                divider=slot > 1,
            )
        self.sections.addWidget(section)

    def _limit_offwork_choices(self, changed: QPushButton, checked: bool) -> None:
        if checked and sum(button.isChecked() for button in self.offwork_buttons) > 2:
            with QSignalBlocker(changed):
                changed.setChecked(False)
            QMessageBox.information(self, "下班提醒", "下班提醒时间最多选2个。")

    def _prevent_duplicate_water(self, changed: GuidedTimeCombo) -> None:
        value = changed.currentData()
        if not value:
            return
        selected = [combo.currentData() for combo in self.water_custom if combo is not changed]
        if value in self.FIXED_WATER_TIMES or value in selected:
            with QSignalBlocker(changed):
                changed.set_value("")
            QMessageBox.information(self, "喝水提醒", "这个时间已经存在，请选择其他时间。")

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
            "water_custom_times": [combo.currentData() or "" for combo in self.water_custom],
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
            "shortcut": self.shortcut.currentData(),
            "fixed_texts": {slot: edit.text().strip() for slot, edit in self.fixed_texts},
        }
