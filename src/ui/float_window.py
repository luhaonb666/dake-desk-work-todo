"""Compact, animated desktop float panel for Work Todo."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPropertyAnimation, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class FloatCard(QFrame):
    """A compact card whose colour indicates countdown or manual content."""

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 3, 6, 3)
        layout.setSpacing(3)
        self.badge = QLabel()
        self.badge.setFixedWidth(20)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.text = QLabel()
        self.text.setWordWrap(False)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.text, 1)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_density(self, height: int) -> None:
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def update_card(self, badge: str, text: str, *, kind: str, highlighted: bool = False) -> None:
        manual_break = "\n" in text
        if highlighted:
            background, border, badge_color = "#ffffff", "#438bd0", "#1766ab"
        elif kind == "countdown":
            background, border, badge_color = "#fff7e8", "#f2d5a7", "#9a6d24"
        else:
            background, border, badge_color = "#f5f7fa", "#dce3eb", "#64707e"
        font_size = 11 if manual_break else 14
        self.setStyleSheet(
            f"background:{background}; border:{'3' if highlighted else '1'}px solid {border}; border-radius:13px; color:#3e4854;"
        )
        self.badge.setText(badge)
        self.badge.setStyleSheet(
            f"border:none; background:transparent; color:{badge_color}; font-size:10px; font-weight:700;"
        )
        shown = text
        if not manual_break and len(text) > 12:
            shown = text[:11] + "…"
        self.text.setText(shown or "暂无固定内容")
        self.text.setStyleSheet(
            f"border:none; background:transparent; color:#3e4854; font-size:{font_size}px; font-weight:600;"
        )


class FloatWindow(QWidget):
    open_requested = pyqtSignal()
    collapsed_after_alert = pyqtSignal()
    position_changed = pyqtSignal(int)

    EXPANDED_WIDTH = 208
    PEEK_WIDTH = 22
    BASE_CARD_HEIGHT = 40
    MAX_UNCOMPRESSED_CARDS = 7

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("工作待办 V1.3 · 浮窗")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self._cards: list[FloatCard] = []
        self._collapsed = False
        self._alert_open = False
        self._temporary_header = False
        self._dock_y: int | None = None
        self._drag_offset = None
        self._block_expand = False
        self._default_header = ""
        self._overtime_header = ""
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self.collapse)
        self._expand_guard_timer = QTimer(self)
        self._expand_guard_timer.setSingleShot(True)
        self._expand_guard_timer.timeout.connect(self._release_expand_guard)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(4)
        self.greeting = QLabel()
        self.greeting.setWordWrap(True)
        self.greeting.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide_button = QPushButton("收起 ›")
        self.hide_button.setMinimumSize(50, 26)
        self.hide_button.setStyleSheet("border:none; color:#526172; background:transparent; padding:4px; font-size:12px;")
        self.hide_button.clicked.connect(self.manual_collapse)
        header.addWidget(self.greeting, 1)
        header.addWidget(self.hide_button, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(header)
        self.greeting.setFixedHeight(24)
        self._apply_header("", "default")

    def configure(self, greeting: str, countdown_count: int, manual_count: int, overtime_header: str = "") -> None:
        self._default_header = greeting
        self._overtime_header = overtime_header
        if not self._temporary_header:
            self._restore_header()
        wanted = countdown_count + manual_count
        while len(self._cards) < wanted:
            card = FloatCard()
            self.layout.addWidget(card)
            self._cards.append(card)
        while len(self._cards) > wanted:
            card = self._cards.pop()
            self.layout.removeWidget(card)
            card.deleteLater()
        height = self.BASE_CARD_HEIGHT
        if wanted > self.MAX_UNCOMPRESSED_CARDS:
            height = max(28, round(self.BASE_CARD_HEIGHT * self.MAX_UNCOMPRESSED_CARDS / wanted))
        for card in self._cards:
            card.set_density(height)
        # Shrink immediately when fewer cards are displayed; otherwise the header
        # receives the old spare height and turns into the large blank box shown in V1.3.
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def _apply_header(self, text: str, mode: str) -> None:
        if mode == "alert":
            background, border, color = "#fffbea", "#ead7a2", "#806628"
        elif mode == "overtime":
            background, border, color = "#e7edf3", "#aab8c7", "#435365"
        else:
            background, border, color = "#e8edf2", "#b7c2cd", "#435365"
        self.greeting.setText(text)
        self.greeting.setStyleSheet(
            f"background:{background}; border:1px solid {border}; border-radius:10px; "
            f"font-size:12px; font-weight:700; color:{color}; padding:3px 6px;"
        )

    def _restore_header(self) -> None:
        if self._overtime_header:
            self._apply_header(self._overtime_header, "overtime")
        else:
            self._apply_header(self._default_header, "default")

    def set_items(self, countdown: list[tuple[str, str, int]], manual: list[tuple[str, str]], highlighted: set[int]) -> None:
        index = 0
        for badge, text, task_id in countdown:
            self._cards[index].update_card(badge, text, kind="countdown", highlighted=task_id in highlighted)
            index += 1
        for badge, text in manual:
            self._cards[index].update_card(badge, text, kind="manual")
            index += 1

    def _screen(self):
        return self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()

    def set_dock_y(self, y: int | None) -> None:
        self._dock_y = y

    def _clamped_y(self, desired_y: int, screen) -> int:
        return max(screen.top() + 12, min(desired_y, screen.bottom() - self.height() - 12))

    def dock_to_right(self, *, collapsed: bool = False) -> None:
        screen = self._screen()
        default_y = max(screen.top() + 30, screen.center().y() - self.height() // 2)
        y = self._clamped_y(self._dock_y if self._dock_y is not None else default_y, screen)
        self._dock_y = y
        x = screen.right() - self.PEEK_WIDTH if collapsed else screen.right() - self.width() - 10
        self.move(x, y)
        self._collapsed = collapsed
        self.hide_button.setText("展开 ‹" if collapsed else "收起 ›")

    def _animate_to(self, target: tuple[int, int]) -> None:
        self._animation.stop()
        self._animation.setDuration(220)
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(QPoint(*target))
        self._animation.start()

    def _release_expand_guard(self) -> None:
        self._block_expand = False

    def expand(self) -> None:
        if self._block_expand:
            return
        self._collapse_timer.stop()
        self._collapsed = False
        self.hide_button.setText("收起 ›")
        screen = self._screen()
        y = self._clamped_y(self.y(), screen)
        self._dock_y = y
        self._animate_to((screen.right() - self.width() - 10, y))

    def collapse(self, *, manual: bool = False) -> None:
        self._collapse_timer.stop()
        self._collapsed = True
        self.hide_button.setText("展开 ‹")
        if manual:
            self._block_expand = True
            self._expand_guard_timer.start(500)
        screen = self._screen()
        y = self._clamped_y(self.y(), screen)
        self._dock_y = y
        self._animate_to((screen.right() - self.PEEK_WIDTH, y))
        if self._alert_open:
            self._alert_open = False
            self._temporary_header = False
            self._restore_header()
            self.collapsed_after_alert.emit()

    def manual_collapse(self) -> None:
        self.collapse(manual=True)

    def toggle_collapsed(self) -> None:
        self.expand() if self._collapsed else self.manual_collapse()

    def show_alert(self, message: str = "") -> None:
        self.show()
        self._block_expand = False
        self._expand_guard_timer.stop()
        if message:
            self._temporary_header = True
            self._apply_header(message, "alert")
        self._alert_open = True
        self.expand()
        self._collapse_timer.start(5_000)

    def enterEvent(self, event):  # noqa: N802
        self._collapse_timer.stop()
        if not self._block_expand:
            self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        if not self._collapsed:
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
            self._dock_y = self._clamped_y(self.y(), self._screen())
            self.position_changed.emit(self._dock_y)
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.open_requested.emit()
        event.accept()
