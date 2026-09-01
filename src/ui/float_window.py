"""Animated, draggable desktop float panel with independent manual slots."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPropertyAnimation, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class FloatCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(50)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 8, 10, 8)
        layout.setSpacing(8)
        self.badge = QLabel()
        self.badge.setFixedWidth(42)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel()
        self.text.setWordWrap(True)
        layout.addWidget(self.badge)
        layout.addWidget(self.text, 1)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def update_card(self, badge: str, text: str, highlighted: bool = False) -> None:
        if highlighted:
            background, border, badge_bg = "#ffe4ed", "#f29db8", "#fa83aa"
        else:
            background, border, badge_bg = "#f8f6ff", "#dfd8f6", "#c6b5ee"
        self.setStyleSheet(f"background:{background}; border:1px solid {border}; border-radius:14px; color:#4b4658;")
        self.badge.setText(badge)
        self.badge.setStyleSheet(
            f"background:{badge_bg}; color:white; border:none; border-radius:9px; padding:5px 2px; font-weight:700;"
        )
        self.text.setText(text or "暂无内容")
        self.text.setStyleSheet("border:none; font-size:13px; color:#4b4658;")


class FloatWindow(QWidget):
    open_requested = pyqtSignal()
    collapsed_after_alert = pyqtSignal()
    position_changed = pyqtSignal(int)
    EXPANDED_WIDTH = 260
    PEEK_WIDTH = 28

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("工作待办 V1.1 · 浮窗")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self._cards: list[FloatCard] = []
        self._collapsed = False
        self._alert_open = False
        self._drag_offset = None
        self._dock_y: int | None = None
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self.collapse)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(7, 7, 7, 7)
        self.layout.setSpacing(6)
        header = QHBoxLayout()
        self.greeting = QLabel()
        self.greeting.setWordWrap(True)
        self.greeting.setStyleSheet("font-size:13px; font-weight:700; color:#766990; padding:4px 5px;")
        self.greeting.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide_button = QPushButton("收起 ›")
        self.hide_button.setStyleSheet("border:none; color:#988aad; background:transparent; padding:3px; font-size:12px;")
        self.hide_button.clicked.connect(self.toggle_collapsed)
        header.addWidget(self.greeting, 1)
        header.addWidget(self.hide_button)
        self.layout.addLayout(header)

    def configure(self, greeting: str, countdown_count: int, manual_count: int) -> None:
        self.greeting.setText(greeting)
        wanted = countdown_count + manual_count
        while len(self._cards) < wanted:
            card = FloatCard()
            self.layout.addWidget(card)
            self._cards.append(card)
        while len(self._cards) > wanted:
            card = self._cards.pop()
            self.layout.removeWidget(card)
            card.deleteLater()

    def set_items(self, countdown: list[tuple[str, str, int]], manual: list[tuple[str, str]], highlighted: set[int]) -> None:
        index = 0
        for badge, text, task_id in countdown:
            self._cards[index].update_card(badge, text, task_id in highlighted)
            index += 1
        for badge, text in manual:
            self._cards[index].update_card(badge, text)
            index += 1

    def _screen(self):
        return self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()

    def set_dock_y(self, y: int | None) -> None:
        self._dock_y = y

    def _clamped_y(self, desired_y: int, screen) -> int:
        return max(screen.top() + 12, min(desired_y, screen.bottom() - self.height() - 12))

    def dock_to_right(self) -> None:
        screen = self._screen()
        default_y = max(screen.top() + 30, screen.center().y() - self.height() // 2)
        y = self._clamped_y(self._dock_y if self._dock_y is not None else default_y, screen)
        self._dock_y = y
        self.move(screen.right() - self.width() - 12, y)

    def _animate_to(self, target) -> None:
        self._animation.stop()
        self._animation.setDuration(240)
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(QPoint(*target))
        self._animation.start()

    def expand(self) -> None:
        self._collapse_timer.stop()
        self._collapsed = False
        self.hide_button.setText("收起 ›")
        screen = self._screen()
        y = self._clamped_y(self.y(), screen)
        self._dock_y = y
        self._animate_to((screen.right() - self.width() - 12, y))

    def collapse(self) -> None:
        self._collapsed = True
        self.hide_button.setText("展开 ‹")
        screen = self._screen()
        y = self._clamped_y(self.y(), screen)
        self._dock_y = y
        self._animate_to((screen.right() - self.PEEK_WIDTH, y))
        if self._alert_open:
            self._alert_open = False
            self.collapsed_after_alert.emit()

    def toggle_collapsed(self) -> None:
        self.expand() if self._collapsed else self.collapse()

    def show_alert(self) -> None:
        self.show()
        self.expand()
        self._alert_open = True
        self._collapse_timer.start(5_000)

    def enterEvent(self, event):  # noqa: N802
        self._collapse_timer.stop()
        self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._collapse_timer.start(4_000)
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            screen = self._screen()
            self._dock_y = self._clamped_y(self.y(), screen)
            self.position_changed.emit(self._dock_y)
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.open_requested.emit()
        event.accept()
