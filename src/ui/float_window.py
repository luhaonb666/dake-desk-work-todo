"""Read-only desktop float panel with six deliberately limited slots."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class FloatWindow(QWidget):
    open_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("工作待办 · 浮窗")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(310)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)
        self.title = QLabel("工作待办")
        self.title.setStyleSheet("font-weight: 600; color: #5f6670; padding: 4px 8px;")
        self.layout.addWidget(self.title)
        self.cards: list[QLabel] = []
        for index in range(6):
            card = QLabel("暂无事项")
            card.setWordWrap(True)
            card.setMinimumHeight(38)
            card.setStyleSheet(self._style(index))
            self.layout.addWidget(card)
            self.cards.append(card)

    @staticmethod
    def _style(index: int) -> str:
        if index < 3:
            return "background:#fff7e8; border:1px solid #f2d5a7; border-radius:10px; padding:8px; color:#744c10;"
        return "background:#f5f7fa; border:1px solid #e2e7ed; border-radius:10px; padding:8px; color:#3e4854;"

    def set_items(self, texts: list[str]) -> None:
        for card, text in zip(self.cards, texts):
            card.setText(text or "暂无事项")

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.open_requested.emit()
        event.accept()
