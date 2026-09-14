"""Optional multi-line execution steps for one to-do item."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class _StepRow(QWidget):
    """One executable step; its detail is intentionally allowed to span lines."""

    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, content: str = "", completed: bool = False, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.check = QCheckBox()
        self.check.setChecked(completed)
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(content)
        self.edit.setPlaceholderText("步骤 1：写下这一步需要做什么；可继续换行补充")
        self.edit.setFixedHeight(58)
        self.edit.setStyleSheet("QPlainTextEdit { padding:5px 7px; }")
        self.remove = QPushButton("×")
        self.remove.setToolTip("删除这一步")
        self.remove.setFixedSize(26, 26)
        self.remove.setStyleSheet(
            "QPushButton { color:#8793a2; background:transparent; border:none; font-size:18px; padding:0; }"
            "QPushButton:hover { color:#a34a4a; background:#f9eaea; border-radius:8px; }"
        )
        row.addWidget(self.check, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(self.remove, 0)
        self.check.toggled.connect(self.changed)
        self.edit.textChanged.connect(self.changed)
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self))

    def value(self) -> dict:
        return {"content": self.edit.toPlainText().strip(), "is_completed": self.check.isChecked()}


class TaskStepsEditor(QWidget):
    """An opt-in step area that starts small and expands on the first click."""

    changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)
        self.start_button = QPushButton("＋ 添加待办步骤")
        self.start_button.setObjectName("stepStartButton")
        self.start_button.setToolTip("为复杂事项增加可逐项勾选的执行步骤。")
        self.start_button.setStyleSheet(
            "QPushButton#stepStartButton { text-align:left; color:#587298; background:#f7faff; "
            "border:1px dashed #abc0df; border-radius:8px; padding:6px 9px; font-weight:600; }"
            "QPushButton#stepStartButton:hover { background:#eef5ff; border-color:#7399d4; }"
        )
        outer.addWidget(self.start_button)

        self.panel = QWidget()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)
        heading = QHBoxLayout()
        title = QLabel("待办步骤")
        title.setStyleSheet("font-size:13px; color:#536273; font-weight:600;")
        heading.addWidget(title)
        heading.addStretch()
        self.add_button = QPushButton("＋ 新建步骤")
        self.add_button.setObjectName("quietButton")
        self.add_button.setToolTip("新建步骤 2、步骤 3……每一步都可写多行。")
        heading.addWidget(self.add_button)
        panel_layout.addLayout(heading)
        self.guide = QLabel("每一步可写多行；勾选步骤只记录进度，整条事项仍由你决定何时完成。")
        self.guide.setWordWrap(True)
        self.guide.setStyleSheet("font-size:11px; color:#8793a2; padding:0 2px;")
        panel_layout.addWidget(self.guide)
        self.rows_host = QWidget()
        self.rows = QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        panel_layout.addWidget(self.rows_host)
        outer.addWidget(self.panel)

        self.start_button.clicked.connect(lambda _checked=False: self.start())
        self.add_button.clicked.connect(lambda _checked=False: self.add_row())
        self._refresh_panel()

    def _rows(self) -> list[_StepRow]:
        return [
            self.rows.itemAt(index).widget()
            for index in range(self.rows.count())
            if isinstance(self.rows.itemAt(index).widget(), _StepRow)
        ]

    def start(self) -> None:
        """Reveal the area and create the first row in the same click."""
        if not self._rows():
            self.add_row()
        else:
            self._refresh_panel()

    def add_row(self, content: str = "", completed: bool = False, *, focus: bool = True) -> None:
        row = _StepRow(content, completed, self.rows_host)
        row.changed.connect(self._on_changed)
        row.remove_requested.connect(self.remove_row)
        self.rows.addWidget(row)
        self._refresh_panel()
        if focus:
            row.edit.setFocus()
        self._on_changed()

    def import_note_lines(self, text: str) -> int:
        """Append one new step for each non-empty note line, never deleting notes."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            self.add_row(line, focus=False)
        return len(lines)

    def remove_row(self, row: _StepRow) -> None:
        self.rows.removeWidget(row)
        row.deleteLater()
        self._refresh_panel()
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
        self._refresh_panel()
        self._refresh_guide()

    def values(self) -> list[dict]:
        return [row.value() for row in self._rows() if row.value()["content"]]

    def _on_changed(self) -> None:
        self._refresh_guide()
        if not self._loading:
            self.changed.emit()

    def _refresh_panel(self) -> None:
        active = bool(self._rows())
        self.start_button.setVisible(not active)
        self.panel.setVisible(active)

    def _refresh_guide(self) -> None:
        values = self.values()
        if values and all(step["is_completed"] for step in values):
            self.guide.setText("所有待办步骤已完成；如整条事项也完成，请勾选事项左侧方框。")
            self.guide.setStyleSheet("font-size:11px; color:#9a6d24; font-weight:600; padding:0 2px;")
        else:
            self.guide.setText("每一步可写多行；勾选步骤只记录进度，整条事项仍由你决定何时完成。")
            self.guide.setStyleSheet("font-size:11px; color:#8793a2; padding:0 2px;")
