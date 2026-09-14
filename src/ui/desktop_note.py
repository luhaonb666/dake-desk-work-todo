"""One editable, resizable desktop note kept separate from to-do items."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui.theme import APP_STYLE


NOTE_COLORS = {
    "warm_yellow": ("米黄", "#fff9e8", "#d8c383", "#5f5134"),
    "soft_green": ("浅绿", "#f1f8ef", "#aec8aa", "#405c47"),
    "mist_blue": ("雾蓝", "#f0f6fb", "#aabfd1", "#405669"),
    "warm_gray": ("暖灰", "#f6f5f2", "#c7c2ba", "#57534e"),
}


class DesktopNoteWindow(QWidget):
    """A single desk-side note with intentional editing and direct resizing."""

    content_saved = pyqtSignal(str)
    layout_changed = pyqtSignal()
    hide_requested = pyqtSignal()

    FOLD_LINES = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._color = "warm_yellow"
        self._fold_long_content = True
        self._expanded = False
        self._editing = False
        self._drag_start: QPoint | None = None
        self._resize_start: QPoint | None = None
        self._start_size = None
        self.setObjectName("desktopNoteWindow")
        self.setWindowTitle("大可桌边 · 桌边便签")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(210, 150)
        self.resize(270, 220)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 9, 10, 9)
        outer.setSpacing(7)
        # The entire blank part of the top bar is a drag handle.  The older
        # version only listened on the few pixels occupied by the title text,
        # which made the note look as though it could not be moved.
        self.drag_handle = QWidget()
        self.drag_handle.setToolTip("拖动此处可移动便签")
        self.drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag_handle.installEventFilter(self)
        header = QHBoxLayout(self.drag_handle)
        header.setContentsMargins(0, 0, 0, 0)
        self.drag_label = QLabel("桌边便签")
        self.drag_label.setToolTip("拖动此处可移动便签")
        self.drag_label.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag_label.setStyleSheet("font-size:13px; font-weight:600; background:transparent; border:none;")
        self.drag_label.installEventFilter(self)
        header.addWidget(self.drag_label, 1)
        self.edit_button = QPushButton("编辑与调整")
        self.edit_button.setToolTip("编辑文字，并拖动右下角调整便签大小")
        self.done_button = QPushButton("完成")
        self.done_button.setVisible(False)
        self.edit_button.clicked.connect(self.enter_editing)
        self.done_button.clicked.connect(self.finish_editing)
        header.addWidget(self.edit_button)
        header.addWidget(self.done_button)
        outer.addWidget(self.drag_handle)

        self.view = QLabel()
        self.view.setTextFormat(Qt.TextFormat.PlainText)
        self.view.setWordWrap(True)
        self.view.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.view.setStyleSheet("font-size:13px; background:transparent; border:none;")
        outer.addWidget(self.view, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("写下临时要记住的内容……")
        self.editor.setVisible(False)
        outer.addWidget(self.editor, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        self.fold_button = QPushButton()
        self.fold_button.setObjectName("quietButton")
        self.fold_button.clicked.connect(self.toggle_expanded)
        bottom.addWidget(self.fold_button)
        bottom.addStretch()
        self.resize_hint = QLabel("↘ 拖动调整大小")
        self.resize_hint.setToolTip("拖动可调整便签宽度和高度")
        self.resize_hint.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.resize_hint.setVisible(False)
        self.resize_hint.installEventFilter(self)
        bottom.addWidget(self.resize_hint)
        outer.addLayout(bottom)
        self._apply_color()
        self._refresh_view()

    def set_note(self, text: str, color: str, fold_long_content: bool) -> None:
        self._text = str(text or "")
        self._color = color if color in NOTE_COLORS else "warm_yellow"
        self._fold_long_content = bool(fold_long_content)
        self._expanded = False
        if not self._editing:
            self.editor.setPlainText(self._text)
        self._apply_color()
        self._refresh_view()

    def note_state(self) -> dict:
        return {
            "text": self._text,
            "color": self._color,
            "fold_long_content": self._fold_long_content,
        }

    def enter_editing(self) -> None:
        self._editing = True
        self.editor.setPlainText(self._text)
        self.view.setVisible(False)
        self.fold_button.setVisible(False)
        self.editor.setVisible(True)
        self.edit_button.setVisible(False)
        self.done_button.setVisible(True)
        self.resize_hint.setVisible(True)
        self.editor.setFocus()

    def finish_editing(self) -> None:
        self._text = self.editor.toPlainText().strip()
        self._editing = False
        self.editor.setVisible(False)
        self.view.setVisible(True)
        self.edit_button.setVisible(True)
        self.done_button.setVisible(False)
        self.resize_hint.setVisible(False)
        self._expanded = False
        self._refresh_view()
        self.content_saved.emit(self._text)
        self.layout_changed.emit()

    def toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._refresh_view()

    def _refresh_view(self) -> None:
        lines = self._text.splitlines()
        has_hidden = self._fold_long_content and len(lines) > self.FOLD_LINES
        if has_hidden and not self._expanded:
            self.view.setText("\n".join(lines[:self.FOLD_LINES]))
            self.fold_button.setText("↓ 展开全文")
            self.fold_button.setVisible(True)
        else:
            self.view.setText(self._text or "还没有内容。点“编辑与调整”写下一段临时记录。")
            self.fold_button.setText("↑ 收起内容")
            self.fold_button.setVisible(has_hidden)

    def _apply_color(self) -> None:
        _name, background, border, text = NOTE_COLORS[self._color]
        self.setStyleSheet(
            f"QWidget#desktopNoteWindow {{ background:{background}; border:1px solid {border}; border-radius:13px; }}"
            f"QLabel {{ color:{text}; }}"
            "QPlainTextEdit { background:rgba(255,255,255,0.45); border:1px solid rgba(100,100,100,0.24); "
            "border-radius:9px; padding:6px; color:#3f4750; }"
            f"QPushButton {{ background:rgba(255,255,255,0.48); border:1px solid {border}; border-radius:8px; color:{text}; padding:4px 7px; }}"
            "QPushButton:hover { background:rgba(255,255,255,0.8); }"
        )

    def eventFilter(self, watched, event):  # noqa: N802
        if watched in (getattr(self, "drag_label", None), getattr(self, "drag_handle", None)):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.globalPosition().toPoint()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_start is not None:
                point = event.globalPosition().toPoint()
                self.move(self.pos() + point - self._drag_start)
                self._drag_start = point
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._drag_start is not None:
                self._drag_start = None
                self.layout_changed.emit()
                return True
        # Qt can dispatch a child-polish event while this window is still
        # constructing.  At that moment ``resize_hint`` is not guaranteed to
        # exist yet, so a harmless event must not turn into a global exception.
        if watched is getattr(self, "resize_hint", None) and self._editing:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._resize_start = event.globalPosition().toPoint()
                self._start_size = self.size()
                return True
            if event.type() == QEvent.Type.MouseMove and self._resize_start is not None:
                delta = event.globalPosition().toPoint() - self._resize_start
                self.resize(max(self.minimumWidth(), self._start_size.width() + delta.x()), max(self.minimumHeight(), self._start_size.height() + delta.y()))
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._resize_start is not None:
                self._resize_start = None
                self.layout_changed.emit()
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):  # noqa: N802
        self.hide_requested.emit()
        event.ignore()
        self.hide()


class DesktopNoteDialog(QDialog):
    """The safe main-page management entry for the single desktop note."""

    def __init__(self, state: dict, visible: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("桌边便签管理")
        self.setMinimumSize(440, 380)
        self.setStyleSheet(APP_STYLE + "QDialog { background:#f7f9fc; }")
        outer = QVBoxLayout(self)
        self.visible_check = QCheckBox("在桌面显示便签")
        self.visible_check.setChecked(visible)
        outer.addWidget(self.visible_check)
        hint = QLabel("用于临时记录与补充信息；它不是待办，不会自动提醒或完成。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:12px; color:#7b8795;")
        outer.addWidget(hint)
        outer.addWidget(QLabel("便签内容"))
        self.text_edit = QPlainTextEdit(state.get("text", ""))
        self.text_edit.setPlaceholderText("写下临时要记住的内容……")
        self.text_edit.setMinimumHeight(180)
        outer.addWidget(self.text_edit, 1)
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("便签颜色"))
        self.color = QComboBox()
        for key, (label, *_rest) in NOTE_COLORS.items():
            self.color.addItem(label, key)
        self.color.setCurrentIndex(max(0, self.color.findData(state.get("color", "warm_yellow"))))
        color_row.addWidget(self.color)
        color_row.addStretch()
        outer.addLayout(color_row)
        self.fold = QCheckBox("长内容折叠显示（超过 8 行时显示摘要）")
        self.fold.setChecked(bool(state.get("fold_long_content", True)))
        outer.addWidget(self.fold)
        help_text = QLabel(
            "桌面操作：点“编辑与调整”后，拖动整个顶部栏可移动；右下角出现“↘ 拖动调整大小”，可直接改变宽高。"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size:11px; color:#8793a2;")
        outer.addWidget(help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存并应用")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict:
        return {
            "text": self.text_edit.toPlainText().strip(),
            "color": self.color.currentData(),
            "fold_long_content": self.fold.isChecked(),
            "visible": self.visible_check.isChecked(),
        }
