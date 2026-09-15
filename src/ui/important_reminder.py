"""A reliable, app-owned reminder window for important timed work."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ImportantReminderWindow(QWidget):
    """Stay visible at the lower-right until each important item is dismissed."""

    dismissed = pyqtSignal(int)
    snoozed = pyqtSignal(int, int)

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
            "QWidget#importantReminderWindow { background:#fffdf9; border:2px solid #d9d1c6; border-radius:16px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("重要事项提醒")
        title.setStyleSheet("font-size:16px; font-weight:600; color:#3d4d61; background:transparent; border:none;")
        heading.addWidget(title)
        heading.addStretch()
        self.queue_label = QLabel()
        self.queue_label.setStyleSheet("font-size:11px; color:#7b8795; background:transparent; border:none;")
        heading.addWidget(self.queue_label)
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("关闭提醒")
        self.close_button.setToolTip("关闭提醒，不会完成待办")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet(
            "QPushButton { color:#667085; background:transparent; border:none; font-size:22px; padding:0; }"
            "QPushButton:hover { color:#3d4d61; background:#f1ece5; border-radius:12px; }"
        )
        self.close_button.clicked.connect(self._dismiss_current)
        heading.addWidget(self.close_button)
        layout.addLayout(heading)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size:12px; color:#7a6b5b; background:transparent; border:none;")
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
        divider.setStyleSheet("color:#e7e0d7; border:none; background:#e7e0d7; max-height:1px;")
        layout.addWidget(divider)
        hint = QLabel("暂时没空可稍后提醒；关闭提醒不会完成待办。")
        hint.setStyleSheet("font-size:11px; color:#7b746d; background:transparent; border:none;")
        layout.addWidget(hint)
        snooze_row = QHBoxLayout()
        snooze_row.setContentsMargins(0, 0, 0, 0)
        snooze_row.setSpacing(7)
        for minutes in (10, 30):
            button = QPushButton(f"从现在起 {minutes} 分钟后")
            button.setToolTip("从点击这一刻开始计算，届时会再次显示这条软件内置顶提醒。")
            button.setStyleSheet(
                "QPushButton { background:#ffffff; border:1px solid #d8d0c7; border-radius:9px; color:#566f91; padding:7px 9px; }"
                "QPushButton:hover { background:#f7f2eb; border-color:#bcb1a5; }"
            )
            button.clicked.connect(lambda _=False, value=minutes: self._snooze_current(value))
            snooze_row.addWidget(button)
        snooze_row.addStretch()
        layout.addLayout(snooze_row)
        self.dismiss_button = QPushButton("关闭提醒")
        self.dismiss_button.setStyleSheet(
            "QPushButton { background:#5877a2; border:none; border-radius:9px; color:white; font-weight:600; padding:8px 14px; }"
            "QPushButton:hover { background:#466488; }"
        )
        self.dismiss_button.clicked.connect(self._dismiss_current)
        layout.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignRight)

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

    def _dismiss_current(self) -> None:
        if self._current_id is not None:
            self.dismissed.emit(self._current_id)

    def _snooze_current(self, minutes: int) -> None:
        if self._current_id is not None:
            self.snoozed.emit(self._current_id, minutes)

    def _refresh(self) -> None:
        if self._current_id is None:
            self.hide()
            return
        task = self._tasks[self._current_id]
        offset = int(task["important_reminder_offset_minutes"]) if "important_reminder_offset_minutes" in task.keys() else 0
        self.time_label.setText(
            f"{task['due_time']} · 提前 {offset} 分钟提醒" if offset else f"{task['due_time']} · 已到提醒时间"
        )
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
        # The reminder must survive while the user is away, but closing it is
        # never a claim that the task itself has been completed.
        self._dismiss_current()
        event.accept()
