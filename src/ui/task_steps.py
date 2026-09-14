"""Optional, deliberately small execution steps for one to-do item."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class _StepRow(QWidget):
    changed = pyqtSignal()
    next_requested = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, content: str = "", completed: bool = False, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.check = QCheckBox()
        self.check.setChecked(completed)
        self.edit = QLineEdit(content)
        self.edit.setPlaceholderText("例如：核对价格")
        self.remove = QPushButton("×")
        self.remove.setToolTip("删除这一步")
        self.remove.setFixedSize(26, 26)
        self.remove.setStyleSheet(
            "QPushButton { color:#8793a2; background:transparent; border:none; font-size:18px; padding:0; }"
            "QPushButton:hover { color:#a34a4a; background:#f9eaea; border-radius:8px; }"
        )
        row.addWidget(self.check)
        row.addWidget(self.edit, 1)
        row.addWidget(self.remove)
        self.check.toggled.connect(self.changed)
        self.edit.textChanged.connect(self.changed)
        self.edit.returnPressed.connect(self.next_requested)
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self))

    def value(self) -> dict:
        return {"content": self.edit.text().strip(), "is_completed": self.check.isChecked()}


class TaskStepsEditor(QWidget):
    """A calm opt-in list: it assists a task but never completes it by itself."""

    changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)
        heading = QHBoxLayout()
        title = QLabel("分项步骤")
        title.setStyleSheet("font-size:13px; color:#536273; font-weight:600;")
        heading.addWidget(title)
        heading.addStretch()
        self.add_button = QPushButton("＋ 添加分项步骤")
        self.add_button.setObjectName("quietButton")
        self.add_button.setToolTip("把复杂事项拆成几步，例如“核价、盖章、发送”。")
        heading.addWidget(self.add_button)
        outer.addLayout(heading)
        self.guide = QLabel("把这条事项的具体内容拆成可勾选的小步骤；全部完成后，仍需勾选整条事项。")
        self.guide.setWordWrap(True)
        self.guide.setStyleSheet("font-size:11px; color:#8793a2; padding:0 2px;")
        outer.addWidget(self.guide)
        self.rows_host = QWidget()
        self.rows = QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(4)
        outer.addWidget(self.rows_host)
        # QPushButton.clicked carries a ``checked`` bool.  Do not pass it as
        # the row's text: on some Qt builds that turns into QLineEdit(False).
        self.add_button.clicked.connect(lambda _checked=False: self.add_row())

    def _rows(self) -> list[_StepRow]:
        return [self.rows.itemAt(index).widget() for index in range(self.rows.count()) if isinstance(self.rows.itemAt(index).widget(), _StepRow)]

    def add_row(self, content: str = "", completed: bool = False, *, focus: bool = True) -> None:
        row = _StepRow(content, completed, self.rows_host)
        row.changed.connect(self._on_changed)
        row.next_requested.connect(lambda: self.add_row())
        row.remove_requested.connect(self.remove_row)
        self.rows.addWidget(row)
        if focus:
            row.edit.setFocus()
        self._on_changed()

    def remove_row(self, row: _StepRow) -> None:
        self.rows.removeWidget(row)
        row.deleteLater()
        self._on_changed()

    def set_steps(self, steps) -> None:
        self._loading = True
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for step in steps or []:
            self.add_row(str(step["content"]), bool(step["is_completed"]), focus=False)
        self._loading = False
        self._refresh_guide()

    def values(self) -> list[dict]:
        return [row.value() for row in self._rows() if row.value()["content"]]

    def _on_changed(self) -> None:
        self._refresh_guide()
        if not self._loading:
            self.changed.emit()

    def _refresh_guide(self) -> None:
        values = self.values()
        if values and all(step["is_completed"] for step in values):
            self.guide.setText("所有分项步骤已完成；如整条事项也完成，请勾选事项左侧方框。")
            self.guide.setStyleSheet("font-size:11px; color:#9a6d24; font-weight:600; padding:0 2px;")
        elif values:
            self.guide.setText("勾选步骤只记录进度；整条事项仍由你决定何时完成。")
            self.guide.setStyleSheet("font-size:11px; color:#8793a2; padding:0 2px;")
        else:
            self.guide.setText("把这条事项的具体内容拆成可勾选的小步骤；全部完成后，仍需勾选整条事项。")
            self.guide.setStyleSheet("font-size:11px; color:#8793a2; padding:0 2px;")
