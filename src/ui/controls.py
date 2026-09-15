"""Shared controls that never change values accidentally under the mouse wheel."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


# One shared working-time grid.  Keeping it here prevents the task editor and
# reminder pickers from slowly drifting into slightly different time options.
TIME_HOURS = tuple(range(7, 23))
TIME_MINUTES = (0, 10, 15, 20, 30, 40, 45, 50)


def normalize_note_text(text: str) -> str:
    """Use one plain-text newline convention across editing and previewing."""
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")


class NoWheelMixin:
    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


class NoWheelComboBox(NoWheelMixin, QComboBox):
    pass


class NoWheelSpinBox(NoWheelMixin, QSpinBox):
    pass


class NoWheelDateEdit(NoWheelMixin, QDateEdit):
    pass


class NoWheelTimeEdit(NoWheelMixin, QTimeEdit):
    pass


class DurationPicker(QWidget):
    """Relative day/hour/minute picker used for reminder offsets."""

    valueChanged = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.days = NoWheelComboBox()
        self.hours = NoWheelComboBox()
        self.minutes = NoWheelComboBox()
        for value in range(0, 31):
            self.days.addItem(f"{value} 天", value)
        for value in range(0, 24):
            self.hours.addItem(f"{value} 时", value)
        for value in TIME_MINUTES:
            self.minutes.addItem(f"{value} 分", value)
        layout.addWidget(self.days)
        layout.addWidget(self.hours)
        layout.addWidget(self.minutes)
        layout.addStretch()
        self.days.currentIndexChanged.connect(self.valueChanged)
        self.hours.currentIndexChanged.connect(self.valueChanged)
        self.minutes.currentIndexChanged.connect(self.valueChanged)

    def minutes_value(self) -> int:
        return int(self.days.currentData()) * 1440 + int(self.hours.currentData()) * 60 + int(self.minutes.currentData())

    def set_minutes_value(self, minutes: int) -> None:
        total = max(0, int(minutes))
        days, remainder = divmod(total, 1440)
        hours, minutes = divmod(remainder, 60)
        self.days.setCurrentIndex(max(0, self.days.findData(min(30, days))))
        self.hours.setCurrentIndex(max(0, self.hours.findData(hours)))
        minute_index = self.minutes.findData(minutes)
        if minute_index < 0:
            self.minutes.addItem(f"{minutes} 分", minutes)
            minute_index = self.minutes.count() - 1
        self.minutes.setCurrentIndex(minute_index)


class WeekDatePickerPanel(QWidget):
    """A compact seven-day selector, with typing reserved for date jumps."""

    date_selected = pyqtSignal(QDate)

    def __init__(self, selected: QDate, parent=None) -> None:
        super().__init__(parent)
        self._center = selected
        self._selected = selected
        self.setMinimumWidth(330)
        self.setStyleSheet(
            "QWidget {background:#f8fafc; color:#475467;} "
            "QLabel#weekRange {font-size:12px; color:#64748b; font-weight:600;} "
            "QPushButton#weekNav {min-width:28px; max-width:28px; min-height:28px; max-height:28px; padding:0; "
            "border-radius:8px; background:#ffffff; border:1px solid #d8e1ee; color:#526172;} "
            "QPushButton#weekDay {min-width:40px; max-width:40px; min-height:45px; max-height:45px; padding:2px; "
            "border-radius:9px; background:#ffffff; border:1px solid #d8e1ee; color:#586474; font-size:11px;} "
            "QPushButton#weekDay:checked {background:#eef2ff; border:1px solid #8faaf2; color:#365dbc; font-weight:600;} "
            "QPushButton#weekConfirm {min-width:42px; max-width:42px; min-height:28px; max-height:28px; padding:0; "
            "border-radius:8px; background:#ffffff; border:1px solid #d8e1ee; color:#526172;} "
            "QLineEdit {background:#ffffff; border:1px solid #d8e1ee; border-radius:8px; padding:5px 7px;}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 9, 9, 9)
        outer.setSpacing(7)
        navigation = QHBoxLayout()
        navigation.setContentsMargins(0, 0, 0, 0)
        self.previous = QPushButton("‹")
        self.previous.setObjectName("weekNav")
        self.next = QPushButton("›")
        self.next.setObjectName("weekNav")
        self.range_label = QLabel()
        self.range_label.setObjectName("weekRange")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.previous.clicked.connect(lambda: self._shift_week(-7))
        self.next.clicked.connect(lambda: self._shift_week(7))
        navigation.addWidget(self.previous)
        navigation.addWidget(self.range_label, 1)
        navigation.addWidget(self.next)
        outer.addLayout(navigation)

        days = QHBoxLayout()
        days.setContentsMargins(0, 0, 0, 0)
        days.setSpacing(4)
        self.day_buttons: list[QPushButton] = []
        self._day_values: list[QDate] = [QDate() for _ in range(7)]
        for index in range(7):
            button = QPushButton()
            button.setObjectName("weekDay")
            button.setCheckable(True)
            button.clicked.connect(lambda _, position=index: self._choose(self._day_values[position]))
            self.day_buttons.append(button)
            days.addWidget(button)
        outer.addLayout(days)

        typed = QHBoxLayout()
        typed.setContentsMargins(0, 0, 0, 0)
        typed.setSpacing(6)
        typed.addWidget(QLabel("输入日期"))
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("YYYY-MM-DD")
        self.confirm = QPushButton("确定")
        self.confirm.setObjectName("weekConfirm")
        self.confirm.setMinimumWidth(42)
        self.confirm.setMaximumWidth(42)
        self.confirm.clicked.connect(self._choose_typed_date)
        self.date_input.returnPressed.connect(self._choose_typed_date)
        typed.addWidget(self.date_input, 1)
        typed.addWidget(self.confirm)
        outer.addLayout(typed)
        self._refresh_days()

    def _shift_week(self, offset: int) -> None:
        self._center = self._center.addDays(offset)
        self._refresh_days()

    def _refresh_days(self) -> None:
        start = self._center.addDays(-3)
        end = start.addDays(6)
        self.range_label.setText(f"{start.month()} 月 {start.day()} 日 – {end.month()} 月 {end.day()} 日")
        today = QDate.currentDate()
        weekdays = ("一", "二", "三", "四", "五", "六", "日")
        for index, button in enumerate(self.day_buttons):
            value = start.addDays(index)
            prefix = "今天" if value == today else f"周{weekdays[value.dayOfWeek() - 1]}"
            button.setText(f"{prefix}\n{value.month():02d}/{value.day():02d}")
            self._day_values[index] = value
            button.setChecked(value == self._selected)
        self.date_input.setText(self._selected.toString("yyyy-MM-dd"))

    def _choose_typed_date(self) -> None:
        value = QDate.fromString(self.date_input.text().strip(), "yyyy-MM-dd")
        if not value.isValid():
            self.date_input.setStyleSheet("border:1px solid #d97777;")
            self.date_input.setFocus()
            self.date_input.selectAll()
            return
        self._choose(value)

    def _choose(self, value) -> None:
        if not isinstance(value, QDate) or not value.isValid():
            return
        self._selected = value
        self.date_selected.emit(value)


class CompactDatePicker(QWidget):
    """A shared date field that avoids the platform-specific full calendar."""

    dateChanged = pyqtSignal(QDate)

    def __init__(self, value: QDate | None = None, parent=None) -> None:
        super().__init__(parent)
        self._date = value if value is not None and value.isValid() else QDate.currentDate()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton()
        self.button.setObjectName("compactDateButton")
        self.button.setMinimumHeight(31)
        self.button.clicked.connect(self._open_picker)
        layout.addWidget(self.button)
        self._refresh_text()

    def date(self) -> QDate:
        return self._date

    def setDate(self, value: QDate) -> None:  # noqa: N802
        if not value.isValid():
            return
        changed = value != self._date
        self._date = value
        self._refresh_text()
        if changed:
            self.dateChanged.emit(value)

    def _refresh_text(self) -> None:
        today = QDate.currentDate()
        prefix = "今天" if self._date == today else ("明天" if self._date == today.addDays(1) else ("昨天" if self._date == today.addDays(-1) else self._date.toString("yyyy 年")))
        self.button.setText(f"{prefix} {self._date.month()} 月 {self._date.day()} 日  ▾")

    def _open_picker(self) -> None:
        menu = QMenu(self)
        menu.setObjectName("weekDateMenu")
        action = QWidgetAction(menu)
        panel = WeekDatePickerPanel(self._date, menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        panel.date_selected.connect(lambda value: (self.setDate(value), menu.close()))
        self._menu = menu
        menu.exec(self.mapToGlobal(QPoint(0, self.height())))


class StepCounter(QWidget):
    """A click-first number picker with comfortably sized step buttons.

    Native QSpinBox arrows are only a few pixels tall on Windows at 125%
    scaling, which made the float-count setting surprisingly hard to adjust.
    """

    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 99
        self._value = 0
        self.setObjectName("stepCounter")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.minus_button = QPushButton("−")
        self.minus_button.setObjectName("stepDown")
        self.minus_button.setFixedSize(32, 31)
        self.value_display = QLineEdit()
        self.value_display.setObjectName("stepValue")
        self.value_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_display.setReadOnly(True)
        self.value_display.setFixedSize(36, 31)
        self.plus_button = QPushButton("+")
        self.plus_button.setObjectName("stepUp")
        self.plus_button.setFixedSize(32, 31)
        for button in (self.minus_button, self.plus_button):
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(350)
            button.setAutoRepeatInterval(90)
        self.minus_button.clicked.connect(lambda: self.setValue(self._value - 1))
        self.plus_button.clicked.connect(lambda: self.setValue(self._value + 1))
        layout.addWidget(self.minus_button)
        layout.addWidget(self.value_display)
        layout.addWidget(self.plus_button)
        self._sync_view()

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        self._minimum, self._maximum = minimum, maximum
        self.setValue(self._value)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:  # noqa: N802
        value = max(self._minimum, min(self._maximum, int(value)))
        if value == self._value:
            self._sync_view()
            return
        self._value = value
        self._sync_view()
        self.valueChanged.emit(value)

    def _sync_view(self) -> None:
        self.value_display.setText(str(self._value))
        self.minus_button.setEnabled(self._value > self._minimum)
        self.plus_button.setEnabled(self._value < self._maximum)

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()
