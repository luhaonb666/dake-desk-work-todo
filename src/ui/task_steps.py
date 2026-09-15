"""Optional multi-line execution steps for one to-do item."""

from __future__ import annotations

import math

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)


class _StepTextEdit(QPlainTextEdit):
    """Expose focus changes so the row shell owns the complete focus border."""

    focus_changed = pyqtSignal(bool)
    confirm_requested = pyqtSignal()

    def focusInEvent(self, event):  # noqa: N802
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event):  # noqa: N802
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def keyPressEvent(self, event):  # noqa: N802
        """Make Enter advance through the form; explicit modified Enter wraps."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                super().keyPressEvent(event)
            else:
                self.confirm_requested.emit()
                event.accept()
            return
        super().keyPressEvent(event)


class _StepRow(QWidget):
    """One executable step; its detail is intentionally allowed to span lines."""

    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)
    insert_requested = pyqtSignal(object)
    confirm_requested = pyqtSignal(object)

    def __init__(self, content: str = "", completed: bool = False, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        # Keep a dedicated bottom safety gap.  At macOS display scaling the
        # native focus stroke can otherwise be painted one pixel outside an
        # exactly fitted row and look as if its lower edge were cut away.
        row.setContentsMargins(0, 0, 0, 4)
        row.setSpacing(6)
        self.check = QCheckBox()
        self.check.setChecked(completed)
        self.edit_shell = QFrame()
        self.edit_shell.setObjectName("stepInputShell")
        shell_layout = QVBoxLayout(self.edit_shell)
        shell_layout.setContentsMargins(2, 2, 2, 2)
        shell_layout.setSpacing(0)
        self.edit = _StepTextEdit()
        self._editing = False
        self.edit.setPlainText(content)
        self.edit.setPlaceholderText("例如：核对报价、盖章确认、提交报告；可继续换行补充")
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.edit.setFrameShape(QFrame.Shape.NoFrame)
        self.edit.setStyleSheet("QPlainTextEdit { padding:4px 5px; border:none; background:#ffffff; }")
        shell_layout.addWidget(self.edit)
        self.insert = QPushButton("＋")
        self.insert.setToolTip("在这一步下方新增步骤")
        self.insert.setFixedSize(26, 26)
        self.insert.setStyleSheet(
            "QPushButton { color:#5d7fb8; background:#f5f8ff; border:1px solid #c8d7f1; "
            "border-radius:8px; font-size:16px; font-weight:600; padding:0; }"
            "QPushButton:hover { color:#315bb7; background:#eaf1ff; border-color:#91ace0; }"
        )
        self.remove = QPushButton("×")
        self.remove.setToolTip("删除这一步")
        self.remove.setFixedSize(26, 26)
        self.remove.setStyleSheet(
            "QPushButton { color:#8793a2; background:transparent; border:none; font-size:18px; padding:0; }"
            "QPushButton:hover { color:#a34a4a; background:#f9eaea; border-radius:8px; }"
        )
        row.addWidget(self.check, 0)
        row.addWidget(self.edit_shell, 1)
        row.addWidget(self.insert, 0)
        row.addWidget(self.remove, 0)
        self.check.toggled.connect(self.changed)
        self.edit.textChanged.connect(self._refresh_height)
        self.edit.textChanged.connect(self.changed)
        self.edit.focus_changed.connect(self._set_editing)
        self.edit.confirm_requested.connect(lambda: self.confirm_requested.emit(self))
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self))
        self.insert.clicked.connect(lambda: self.insert_requested.emit(self))
        self._refresh_height()
        self._refresh_focus_border(False)

    def _set_editing(self, focused: bool) -> None:
        self._editing = focused
        self._refresh_focus_border(focused)
        self._refresh_height()
        if not focused:
            # QTextDocument completes line layout after focus processing on
            # some platform styles. Recheck once that finishes so a genuine
            # two-line step cannot collapse to one scrollable line.
            QTimer.singleShot(0, self._refresh_height)

    def _refresh_focus_border(self, focused: bool) -> None:
        color = "#7f9cf1" if focused else "#d8e1ee"
        width = 2 if focused else 1
        self.edit_shell.setStyleSheet(
            "QFrame#stepInputShell {"
            f"background:#ffffff; border:{width}px solid {color}; border-radius:9px;"
            "}"
        )

    def _refresh_height(self) -> None:
        """Use calm browse/edit states instead of resizing on every typed line.

        Saved steps browse at their real number of lines.  Focusing any step,
        even an old one-line step, reserves a stable three-line writing area.
        Only explicit Shift/Alt+Enter line breaks beyond that grow the editor,
        capped at four-and-a-half lines with an internal scrollbar.
        """
        line_height = max(1, self.edit.fontMetrics().lineSpacing())
        stored_lines = max(1, self.edit.document().blockCount())
        visible_lines = float(stored_lines)
        if self._editing:
            visible_lines = max(3.0, visible_lines)
        visible_lines = min(4.5, visible_lines)
        height = math.ceil(visible_lines * line_height) + 18
        self.edit_shell.setFixedHeight(height)
        # The shell fits above the layout's dedicated bottom margin, so the
        # complete rounded selection border remains visible on every row.
        self.setFixedHeight(height + 4)

    def value(self) -> dict:
        return {"content": self.edit.toPlainText().strip(), "is_completed": self.check.isChecked()}


class TaskStepsEditor(QWidget):
    """An opt-in step area that starts small and expands on the first click."""

    changed = pyqtSignal()
    structure_changed = pyqtSignal()
    next_field_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        panel_layout.setSpacing(4)
        heading = QHBoxLayout()
        title = QLabel("待办步骤")
        title.setStyleSheet("font-size:13px; color:#536273; font-weight:600;")
        heading.addWidget(title)
        self.guide = QLabel("示例：核对报价、盖章确认、提交报告。勾选只记录进度。")
        self.guide.setToolTip("每一步可写多行；全部步骤完成后，整条事项仍由你自己决定何时完成。")
        self.guide.setStyleSheet("font-size:11px; color:#8a97a8; padding-left:8px;")
        heading.addWidget(self.guide, 1)
        panel_layout.addLayout(heading)
        self.rows_host = QWidget()
        self.rows = QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(2)
        panel_layout.addWidget(self.rows_host)
        outer.addWidget(self.panel)

        self.start_button.clicked.connect(lambda _checked=False: self.start())
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

    def _new_row(self, content: str = "", completed: bool = False) -> _StepRow:
        row = _StepRow(content, completed, self.rows_host)
        row.changed.connect(self._on_changed)
        row.remove_requested.connect(self.remove_row)
        row.insert_requested.connect(self.insert_after)
        row.confirm_requested.connect(self.confirm_row)
        return row

    def add_row(self, content: str = "", completed: bool = False, *, focus: bool = True) -> None:
        row = self._new_row(content, completed)
        self.rows.addWidget(row)
        self._refresh_panel()
        if focus:
            row.edit.setFocus()
        self._on_changed()
        if not self._loading:
            self.structure_changed.emit()

    def insert_after(self, existing: _StepRow) -> None:
        """Create the next step beside the row the user is currently writing."""
        rows = self._rows()
        try:
            index = rows.index(existing) + 1
        except ValueError:
            index = self.rows.count()
        row = self._new_row()
        self.rows.insertWidget(index, row)
        self._refresh_panel()
        row.edit.setFocus()
        self._on_changed()
        if not self._loading:
            self.structure_changed.emit()

    def confirm_row(self, existing: _StepRow) -> None:
        """Enter advances to the next step, then to the body after the last."""
        rows = self._rows()
        try:
            next_row = rows[rows.index(existing) + 1]
        except (ValueError, IndexError):
            self.next_field_requested.emit()
            return
        # Also update the deterministic visual state before Qt delivers the
        # focus event.  This keeps keyboard navigation stable in both a shown
        # window and the editor's off-screen construction path.
        next_row._set_editing(True)
        next_row.edit.setFocus()

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
        if not self._loading:
            self.structure_changed.emit()

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
        self.structure_changed.emit()

    def values(self) -> list[dict]:
        return [row.value() for row in self._rows() if row.value()["content"]]

    def row_count(self) -> int:
        """Count visible editing rows, including a newly created blank first step."""
        return len(self._rows())

    def _on_changed(self) -> None:
        self._refresh_guide()
        self.updateGeometry()
        if not self._loading:
            self.changed.emit()

    def _refresh_panel(self) -> None:
        active = bool(self._rows())
        self.start_button.setVisible(not active)
        self.panel.setVisible(active)
        self.updateGeometry()

    def _refresh_guide(self) -> None:
        values = self.values()
        if values and all(step["is_completed"] for step in values):
            self.guide.setText("步骤已全部完成；请自行勾选整条事项。")
            self.guide.setToolTip("步骤勾选只记录进度；整条事项仍由你决定何时完成。")
            self.guide.setStyleSheet("font-size:11px; color:#9a6d24; font-weight:600; padding-left:8px;")
        else:
            self.guide.setText("示例：核对报价、盖章确认、提交报告。勾选只记录进度。")
            self.guide.setToolTip("每一步可写多行；全部步骤完成后，整条事项仍由你自己决定何时完成。")
            self.guide.setStyleSheet("font-size:11px; color:#8a97a8; padding-left:8px;")
