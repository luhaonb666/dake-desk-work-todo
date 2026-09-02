"""Shared controls that never change values accidentally under the mouse wheel."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QTimeEdit, QWidget


# One shared working-time grid.  Keeping it here prevents the task editor and
# reminder pickers from slowly drifting into slightly different time options.
TIME_HOURS = tuple(range(7, 23))
TIME_MINUTES = (0, 10, 15, 20, 30, 40, 45, 50)


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
