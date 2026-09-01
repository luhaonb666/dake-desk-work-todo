"""Shared controls that never change values accidentally under the mouse wheel."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QDateEdit, QSpinBox, QTimeEdit


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
