"""Single-line, elided labels used by the compact task-step preview."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel


class ElidedStepPreviewLine(QLabel):
    """Keep one saved step on one preview row without hiding its ending."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setWordWrap(False)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)

    def resizeEvent(self, event):  # noqa: N802
        available = max(0, self.contentsRect().width())
        self.setText(self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, available))
        super().resizeEvent(event)
