"""A reliable, app-owned reminder window for important timed work."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ImportantReminderWindow(QWidget):
    """Stay visible at the lower-right until each important item is acknowledged."""

    acknowledged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tasks: dict[int, object] = {}
        self._order: list[int] = []
        self._current_id: int | None = None
        self.setObjectName("importantReminderWindow")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedWidth(332)
        self.setStyleSheet(
            "QWidget#importantReminderWindow { background:#fffaf0; border:2px solid #d59116; border-radius:16px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("重要事项提醒")
        title.setStyleSheet("font-size:16px; font-weight:600; color:#8a5600; background:transparent; border:none;")
        heading.addWidget(title)
        heading.addStretch()
        self.queue_label = QLabel()
        self.queue_label.setStyleSheet("font-size:11px; color:#9a6d24; background:transparent; border:none;")
        heading.addWidget(self.queue_label)
        layout.addLayout(heading)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size:12px; color:#a16b14; background:transparent; border:none;")
        layout.addWidget(self.time_label)
        self.task_title = QLabel()
        self.task_title.setWordWrap(True)
        self.task_title.setStyleSheet("font-size:17px; font-weight:600; color:#344054; background:transparent; border:none;")
        layout.addWidget(self.task_title)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setMaximumHeight(76)
        self.notes.setStyleSheet("font-size:12px; color:#667085; background:transparent; border:none;")
        layout.addWidget(self.notes)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color:#efd9ad; border:none; background:#efd9ad; max-height:1px;")
        layout.addWidget(divider)
        hint = QLabel("此提醒会一直保留，直到你手动确认。")
        hint.setStyleSheet("font-size:11px; color:#9b7a42; background:transparent; border:none;")
        layout.addWidget(hint)
        self.ack_button = QPushButton("我已处理")
        self.ack_button.setStyleSheet(
            "QPushButton { background:#d48a0b; border:none; border-radius:9px; color:white; font-weight:600; padding:8px 14px; }"
            "QPushButton:hover { background:#b87608; }"
        )
        self.ack_button.clicked.connect(self._acknowledge_current)
        layout.addWidget(self.ack_button, 0, Qt.AlignmentFlag.AlignRight)

    def sync_tasks(self, tasks) -> None:
        """Replace the current pending set without dismissing an active reminder."""
        incoming = {int(task["id"]): task for task in tasks}
        new_order = [task_id for task_id in self._order if task_id in incoming]
        new_order.extend(task_id for task_id in incoming if task_id not in new_order)
        self._tasks = incoming
        self._order = new_order
        if self._current_id not in incoming:
            self._current_id = None
        if self._current_id is None and self._order:
            self._current_id = self._order[0]
        self._refresh()

    def remove_task(self, task_id: int) -> None:
        self._tasks.pop(task_id, None)
        self._order = [value for value in self._order if value != task_id]
        if self._current_id == task_id:
            self._current_id = self._order[0] if self._order else None
        self._refresh()

    def _acknowledge_current(self) -> None:
        if self._current_id is not None:
            self.acknowledged.emit(self._current_id)

    def _refresh(self) -> None:
        if self._current_id is None:
            self.hide()
            return
        task = self._tasks[self._current_id]
        self.time_label.setText(f"{task['due_time']} · 已到提醒时间")
        self.task_title.setText(str(task["title"]))
        self.notes.setText(str(task["notes"]).strip() or "请在方便时处理这件重要事项。")
        waiting = max(0, len(self._order) - 1)
        self.queue_label.setText(f"另有 {waiting} 项待处理" if waiting else "")
        self._place_at_lower_right()
        self.show()
        self.raise_()

    def _place_at_lower_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.adjustSize()
        self.move(area.right() - self.width() - 22, area.bottom() - self.height() - 22)

    def closeEvent(self, event):  # noqa: N802
        # Alt+F4 and the title-bar close path must not silently defeat a
        # persistent important reminder.  “我已处理” is the only dismissal.
        event.ignore()
