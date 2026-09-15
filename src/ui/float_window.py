"""Compact, animated desktop float panel for DaKe Desk."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPropertyAnimation, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class FloatBadge(QWidget):
    """Paint compact time with tabular digits, plus manual slot numbers."""

    def __init__(self) -> None:
        super().__init__()
        # A plain QWidget has no useful height hint on Windows. In V1.6.1 the
        # layout compressed this badge to zero height, hiding every time value.
        self.setFixedSize(23, 28)
        self.value = ""
        self.color = QColor("#64707e")

    def _badge_font(self, pixel_size: int) -> QFont:
        """Use Windows' tabular digits so 14:00 and 15:10 balance equally."""
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        font.setPixelSize(pixel_size)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def set_value(self, value: str, color: str) -> None:
        self.value = value
        self.color = QColor(color)
        self.update()

    def set_badge_height(self, height: int) -> None:
        self.setFixedSize(23, max(26, height))

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.color)
        if ":" in self.value:
            hour, minute = self.value.split(":", 1)
            font = self._badge_font(13)
            painter.setFont(font)
            half = self.height() // 2
            # V3.2 keeps hour and minute on exactly the same vertical axis. Their
            # two bounding rectangles meet at the centre so the lines sit closer
            # together without losing the narrow badge footprint.
            painter.drawText(
                QRect(0, 1, self.width(), half - 1),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                hour,
            )
            painter.drawText(
                QRect(0, half, self.width(), self.height() - half - 1),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                minute,
            )
            painter.setPen(QPen(self.color, 1))
            painter.drawLine(9, half, 14, half)
        else:
            # Priority-slot numbers are a touch larger than before, but remain
            # deliberately top-aligned instead of becoming centred ornaments.
            font = self._badge_font(15)
            painter.setFont(font)
            painter.drawText(
                QRect(0, 1, self.width(), max(16, self.height() // 2 + 5)),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self.value,
            )
        painter.end()


class FloatCard(QFrame):
    """A compact card whose colour indicates countdown or manual content."""

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        # The left edge is the part that remains visible when the panel docks
        # off the right side of the screen. Keep the time badge close to that
        # edge so the compact peek can reveal a complete time, not just a sliver.
        layout.setContentsMargins(1, 3, 6, 3)
        layout.setSpacing(3)
        self.badge = FloatBadge()
        self.text = QLabel()
        self.text.setWordWrap(False)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.text, 1)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._kind = "manual"
        self._highlighted = False
        self._pulse_on = False
        self._badge_text = ""
        self._badge_color = "#64707e"

    def set_density(self, height: int) -> None:
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.badge.set_badge_height(height - 6)

    def update_card(
        self,
        badge: str,
        text: str,
        *,
        kind: str,
        highlighted: bool = False,
        source: str = "task",
    ) -> None:
        manual_break = "\n" in text
        self._kind = kind
        self._highlighted = highlighted
        self._pulse_on = False
        self._badge_text = badge
        # Real, single-line work is the most useful glanceable content. Fixed
        # fallback phrases keep their existing quieter size.
        font_size = 11 if manual_break else (16 if source == "task" else 15)
        font_weight = 500 if manual_break else 600
        shown = text
        if not manual_break and len(text) > 12:
            shown = text[:11] + "…"
        is_empty = not bool(text)
        if is_empty:
            # Empty cards are visual placeholders, not an item demanding the
            # user's attention. Keep them deliberately quiet and two visual
            # size steps below a real single-line task.
            text_color, font_weight, font_size = "#bac2cc", 400, 11
        elif source == "fixed_text":
            # A configured empty-slot phrase is still content, just softer
            # than a real task. Keep it visibly above “暂无固定内容”.
            text_color, font_weight = "#768393", 550
        else:
            text_color, font_weight = "#3e4854", font_weight
        self.text.setText(shown or "暂无固定内容")
        self.text.setStyleSheet(
            f"border:none; background:transparent; color:{text_color}; font-size:{font_size}px; font-weight:{font_weight};"
        )
        self._apply_style()

    def set_pulse(self, enabled: bool) -> None:
        if self._highlighted:
            self._pulse_on = enabled
            self._apply_style()

    def _apply_style(self) -> None:
        if self._highlighted:
            background = "#fff0a8" if self._pulse_on else "#ffffff"
            border, badge_color, width = "#c88a08", "#9a6100", 3
        elif self._kind == "countdown":
            background, border, badge_color, width = "#fff7e8", "#f2d5a7", "#9a6d24", 1
        else:
            background, border, badge_color, width = "#f5f7fa", "#dce3eb", "#64707e", 1
        self._badge_color = badge_color
        self.setStyleSheet(
            f"background:{background}; border:{width}px solid {border}; border-radius:13px; color:#3e4854;"
        )
        self.badge.set_value(self._badge_text, badge_color)


class FloatWindow(QWidget):
    open_requested = pyqtSignal()
    collapsed_after_alert = pyqtSignal()
    position_changed = pyqtSignal(int)

    EXPANDED_WIDTH = 208
    # About 15% of the narrow float: the time badge sits tight against the
    # left edge, so this reveals the full enlarged time without exposing card
    # copy or a sliver of the header.
    PEEK_WIDTH = 31
    BASE_CARD_HEIGHT = 40
    MAX_UNCOMPRESSED_CARDS = 7

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("大可桌边 V4.5.8 · 浮窗")
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
        # Dialogs can leave this desktop panel observable without allowing a
        # second, competing action path while the form is unfinished.
        self._passive_mode = False
        self._default_header = ""
        self._overtime_header = ""
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self.collapse)
        self._expand_guard_timer = QTimer(self)
        self._expand_guard_timer.setSingleShot(True)
        self._expand_guard_timer.timeout.connect(self._release_expand_guard)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(420)
        self._pulse_timer.timeout.connect(self._advance_pulse)
        self._pulse_step = 0
        self._pulse_header = False
        self._alert_message = ""
        self._header_font_px = 12
        self._header_mode = "default"
        self._auto_collapse_ms: int | None = 4_000

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
        self.hide_button.setStyleSheet(
            "QPushButton {background:#f3f5f7; border:1px solid #c9d1da; border-radius:9px; "
            "color:#526172; padding:4px; font-size:12px; font-weight:600;} "
            "QPushButton:hover {background:#ffffff; border-color:#aeb9c5;} "
            "QPushButton:pressed {background:#e3e8ed;}"
        )
        self.hide_button.clicked.connect(self.manual_collapse)
        header.addWidget(self.greeting, 1)
        header.addWidget(self.hide_button, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(header)
        self.greeting.setMinimumHeight(24)
        self._apply_header("", "default")

    def configure(
        self,
        greeting: str,
        countdown_count: int,
        manual_count: int,
        overtime_header: str = "",
        auto_collapse_delay: str = "4",
    ) -> None:
        self.set_auto_collapse_delay(auto_collapse_delay)
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
            height = max(34, round(self.BASE_CARD_HEIGHT * self.MAX_UNCOMPRESSED_CARDS / wanted))
        for card in self._cards:
            card.set_density(height)
        # Shrink immediately when fewer cards are displayed; otherwise the header
        # receives the old spare height and turns into the large blank box shown in V1.3.
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def set_auto_collapse_delay(self, value: str | int | None) -> None:
        """Set one shared policy for hover and reminder automatic collapse."""
        self._auto_collapse_ms = None if value in {None, "manual"} else int(value) * 1_000
        if self._auto_collapse_ms is None:
            self._collapse_timer.stop()

    def set_passive_mode(self, enabled: bool) -> None:
        """Keep hover/alerts active while disabling every float click action."""
        self._passive_mode = enabled
        self.hide_button.setEnabled(not enabled)

    def _start_auto_collapse(self) -> None:
        if self._auto_collapse_ms is not None:
            self._collapse_timer.start(self._auto_collapse_ms)

    def _apply_header(self, text: str, mode: str) -> None:
        if mode == "alert":
            background = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fff8c8,stop:0.46 #d9a72e,stop:0.54 #fff4ad,stop:1 #b67b0d)"
            border, color, width = "#9f6800", "#4d3600", 2
        elif mode == "overtime":
            background = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f7f9fb,stop:0.45 #aebbc8,stop:0.54 #edf2f6,stop:1 #94a3b2)"
            border, color, width = "#8695a5", "#334455", 1
        else:
            background = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:0.44 #b9c4cf,stop:0.53 #f1f4f7,stop:1 #9eabb8)"
            border, color, width = "#8998a7", "#334455", 1
        self._header_mode = mode
        self.greeting.setText(text)
        self._resize_header_for_text(text, strict_two_lines=mode in {"alert", "overtime"})
        self.greeting.setStyleSheet(
            f"background:{background}; border:{width}px solid {border}; border-radius:10px; "
            f"font-size:{self._header_font_px}px; font-weight:600; color:{color}; padding:3px 6px;"
        )

    def _resize_header_for_text(self, text: str, *, strict_two_lines: bool = False) -> None:
        """Keep short encouragement compact, but never crop a long reminder."""
        logical_lines = text.splitlines() or [""]
        available_width = max(80, self.EXPANDED_WIDTH - 6 * 2 - 50 - 4 - 14)
        font_px = 12
        if strict_two_lines:
            # Reminder text is authored as exactly two lines. Measure the actual
            # installed font (including Windows 125% DPI) and shrink only enough
            # to keep either line from being wrapped by QLabel.
            while font_px > 9:
                font = QFont(self.greeting.font())
                font.setPixelSize(font_px)
                font.setWeight(QFont.Weight.DemiBold)
                if max(QFontMetrics(font).horizontalAdvance(line) for line in logical_lines) <= available_width:
                    break
                font_px -= 1
            self.greeting.setWordWrap(False)
            font = QFont(self.greeting.font())
            font.setPixelSize(font_px)
            font.setWeight(QFont.Weight.DemiBold)
            line_height = QFontMetrics(font).height()
            height = max(38, 8 + line_height * len(logical_lines))
        else:
            self.greeting.setWordWrap(True)
            font = QFont(self.greeting.font())
            font.setPixelSize(font_px)
            font.setWeight(QFont.Weight.DemiBold)
            bounds = QFontMetrics(font).boundingRect(
                QRect(0, 0, available_width, 120),
                int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                text,
            )
            height = max(24, min(96, bounds.height() + 8))
        self._header_font_px = font_px
        self.greeting.setFixedHeight(height)
        # Recalculate the frameless top-level window as the header expands or
        # returns to normal after a temporary reminder.
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def _restore_header(self) -> None:
        if self._overtime_header:
            self._apply_header(self._overtime_header, "overtime")
        else:
            self._apply_header(self._default_header, "default")

    def set_items(
        self,
        countdown: list[tuple[str, str, int, str]],
        manual: list[tuple[str, str, str]],
        highlighted: set[int],
    ) -> None:
        index = 0
        for badge, text, task_id, source in countdown:
            self._cards[index].update_card(
                badge,
                text,
                kind="countdown",
                highlighted=task_id in highlighted,
                source=source,
            )
            index += 1
        for badge, text, source in manual:
            self._cards[index].update_card(badge, text, kind="manual", source=source)
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
        self.hide_button.setVisible(True)
        if self._temporary_header and self._alert_message:
            self._apply_header(self._alert_message, "alert")
        else:
            self._restore_header()
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
            self._stop_pulse()
            self._alert_open = False
            self._temporary_header = False
            self._restore_header()
            self.collapsed_after_alert.emit()
        # The collapsed sliver is for time and priority-slot recognition, not
        # a clipped fragment of a greeting. Keep the header's geometry stable
        # while making its words and control unavailable off-screen.
        self.greeting.setText("")
        self.greeting.setStyleSheet("background:transparent; border:none;")
        self.hide_button.setVisible(False)

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
        self._pulse_header = bool(message)
        self._alert_message = message
        self._pulse_step = 0
        self._pulse_timer.start()
        self._alert_open = True
        self.expand()
        self._start_auto_collapse()

    def _advance_pulse(self) -> None:
        self._pulse_step += 1
        on = self._pulse_step % 2 == 1
        if self._pulse_header and self._alert_message:
            if on:
                self.greeting.setStyleSheet(
                    "background:#fff9d7; border:3px solid #c38808; border-radius:10px; "
                    f"font-size:{self._header_font_px}px; font-weight:600; color:#4d3600; padding:2px 5px;"
                )
            else:
                self._apply_header(self._alert_message, "alert")
        else:
            for card in self._cards:
                card.set_pulse(on)
        if self._pulse_step >= 6:
            self._pulse_timer.stop()
            if self._pulse_header and self._alert_message:
                self._apply_header(self._alert_message, "alert")
            for card in self._cards:
                card.set_pulse(False)

    def _stop_pulse(self) -> None:
        self._pulse_timer.stop()
        for card in self._cards:
            card.set_pulse(False)

    def enterEvent(self, event):  # noqa: N802
        self._collapse_timer.stop()
        if not self._block_expand:
            self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        if not self._collapsed:
            self._start_auto_collapse()
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if self._passive_mode:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._passive_mode:
            event.accept()
            return
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._passive_mode:
            event.accept()
            return
        if self._drag_offset is not None:
            self._dock_y = self._clamped_y(self.y(), self._screen())
            self.position_changed.emit(self._dock_y)
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if self._passive_mode:
            event.accept()
            return
        self.open_requested.emit()
        event.accept()
