"""The editable DaKe Desk window and its compact desktop float panel."""

from __future__ import annotations

import json
import logging
import random
import sys
from datetime import datetime, timedelta

from PyQt6.QtCore import QDate, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSystemTrayIcon,
    QTabBar, QVBoxLayout, QWidget,
)

from app_paths import app_data_dir
from storage.database import Database
from ui.controls import NoWheelDateEdit
from ui.float_window import FloatWindow
from ui.settings_dialog import SettingsDialog
from ui.task_dialog import TaskDialog
from ui.theme import APP_STYLE, TASK_CARD_COLORS


APP_NAME = "大可桌边"
APP_VERSION = "3.7.2"


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#4f7cff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "✓")
    painter.end()
    return QIcon(pixmap)


class TaskCard(QFrame):
    def __init__(self, task, on_complete, on_edit, on_float, on_delete, parent=None, preview: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("taskCard")
        overdue = bool(task["due_time"] and not task["is_completed"] and datetime.strptime(
            f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M"
        ) < datetime.now())
        state = "preview" if preview else ("fixed" if task["is_fixed"] else ("overdue" if overdue else "normal"))
        color, border = TASK_CARD_COLORS[state]
        self.setStyleSheet(f"QFrame#taskCard {{background:{color}; border:1px solid {border}; border-radius:12px;}}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)
        check = QCheckBox()
        check.setChecked(bool(task["is_completed"]))
        check.toggled.connect(lambda checked: on_complete(task["id"], checked))
        layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(2)
        heading = f"{task['due_time']}  {task['title']}" if task["due_time"] else task["title"]
        title = QLabel(heading)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:15px; font-weight:500; color:#8c939d; text-decoration:line-through;"
            if task["is_completed"] else "font-size:15px; font-weight:500; color:#26313e;"
        )
        content.addWidget(title)
        if task["notes"]:
            notes = QLabel(task["notes"])
            notes.setWordWrap(True)
            notes.setStyleSheet("font-size:12px; color:#718096;")
            content.addWidget(notes)
        if overdue:
            warning = QLabel("已超时")
            warning.setStyleSheet("font-size:12px; color:#bd5b5b; margin-top:2px;")
            content.addWidget(warning)
        layout.addLayout(content, 1)
        for text, callback in (("编辑", lambda: on_edit(task)), ("重点位", lambda: on_float(task)), ("删除", lambda: on_delete(task))):
            button = QPushButton(text)
            button.setObjectName("quietButton")
            button.clicked.connect(callback)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)


class MainWindow(QMainWindow):
    DEFAULT_GREETINGS = [
        "我为亚泰添砖加瓦",
        "工作辛苦\n你也要保持开心鸭！",
        "慢慢推进\n今天非常棒！",
    ]
    EDITOR_BRAND_GREETINGS = [
        "让要紧的事，在桌边等你。",
        "大可桌边，只在需要时提醒你。",
        "工作在推进，生活也别忘了照顾。",
        "今天也要对自己好一点。",
        "忙一点没关系，慢一点也没关系。",
    ]
    WEEKEND_BRAND_GREETINGS = [
        "周末还在推进，辛苦啦。",
        "周末也在认真生活和工作，别忘了照顾自己。",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.db = Database(app_data_dir() / "work-todo.db")
        self.db.ensure_settings_table()
        self._ensure_v21_greetings()
        self._ensure_v32_greetings()
        self._ensure_v35_float_hint()
        self._ensure_v37_float_hint_copy()
        self.setWindowTitle(f"{APP_NAME} V{APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(760, 760)
        self.setMinimumSize(570, 520)
        self.float_window = FloatWindow()
        self.float_window.open_requested.connect(self.show_editor)
        self.float_window.collapsed_after_alert.connect(self.finish_float_alert)
        self.float_window.position_changed.connect(self.save_float_position)
        stored_y = self.db.get_setting("float_dock_y", "")
        if stored_y.isdigit():
            self.float_window.set_dock_y(int(stored_y))
        self.alert_task_ids: set[int] = set()
        self.hotkey_manager = None
        self._build_ui()
        self._build_tray()
        self.set_autostart(self.db.get_setting("autostart", "1") == "1")
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(30_000)
        self.brand_timer = QTimer(self)
        self.brand_timer.setSingleShot(True)
        self.brand_timer.timeout.connect(self._refresh_brand_at_hour)
        self._schedule_next_brand_hour()
        self.render()
        QTimer.singleShot(250, self.restore_float)
        QTimer.singleShot(1_000, self.check_reminders)

    def _ensure_v21_greetings(self) -> None:
        """Migrate built-in wording and remove the retired fourth greeting."""
        if self.db.get_setting("greetings_v210_seeded", "0") == "1":
            return
        try:
            saved = json.loads(self.db.get_setting("saved_float_greetings", ""))
            if not isinstance(saved, list):
                saved = []
        except json.JSONDecodeError:
            saved = []
        replacements = {
            "工作辛苦，你也要保持开心鸭！": self.DEFAULT_GREETINGS[1],
            "慢慢推进，今天也很棒！": self.DEFAULT_GREETINGS[2],
        }
        removed_defaults = {"稳稳完成眼前这一件就好。"}
        migrated: list[str] = []
        for text in [*self.DEFAULT_GREETINGS, *saved]:
            if not isinstance(text, str) or not text.strip():
                continue
            text = replacements.get(text.strip(), text.strip())
            if text in removed_defaults:
                continue
            if text not in migrated:
                migrated.append(text)
        current = self.db.get_setting("float_greeting", self.DEFAULT_GREETINGS[0]).strip()
        current = replacements.get(current, current)
        if current in removed_defaults:
            current = self.DEFAULT_GREETINGS[0]
        if current and current not in migrated:
            migrated.append(current)
        self.db.set_setting("saved_float_greetings", json.dumps(migrated, ensure_ascii=False))
        self.db.set_setting("float_greeting", current or (migrated[0] if migrated else ""))
        self.db.set_setting("greetings_v210_seeded", "1")

    @staticmethod
    def _limit_greeting_lines(text: str) -> str:
        """Keep float encouragement compact and readable at three lines."""
        return "\n".join(text.strip().splitlines()[:3])

    def _ensure_v32_greetings(self) -> None:
        """Remove the reported typo and cap legacy custom greetings at three lines."""
        if self.db.get_setting("greetings_v320_seeded", "0") == "1":
            return
        try:
            saved = json.loads(self.db.get_setting("saved_float_greetings", ""))
        except json.JSONDecodeError:
            saved = []
        corrected = "我为亚泰添砖加瓦"
        typo = "我为亚泰添砖贴瓦"
        cleaned: list[str] = []
        for item in saved if isinstance(saved, list) else []:
            if not isinstance(item, str):
                continue
            text = self._limit_greeting_lines(item)
            if not text:
                continue
            if text == typo:
                text = corrected
            if text not in cleaned:
                cleaned.append(text)
        if corrected not in cleaned:
            cleaned.insert(0, corrected)
        current = self._limit_greeting_lines(self.db.get_setting("float_greeting", corrected))
        if current == typo or not current:
            current = corrected
        if current not in cleaned:
            cleaned.append(current)
        self.db.set_setting("saved_float_greetings", json.dumps(cleaned, ensure_ascii=False))
        self.db.set_setting("float_greeting", current)
        self.db.set_setting("greetings_v320_seeded", "1")

    def _ensure_v35_float_hint(self) -> None:
        """Seed the float's double-click hint without changing user ordering.

        A new profile gets the hint in priority slot 1.  On upgrade, the first
        user phrase stays first; the hint may use slot 2 only when slot 2 is
        empty.  If it is occupied, there is no unobtrusive safe place for it.
        """
        if self.db.get_setting("float_hint_v350_seeded", "0") == "1":
            return
        hint = "双击浮窗可打开主页面"
        first = self.db.get_setting("float_text_1", "").strip()
        second = self.db.get_setting("float_text_2", "").strip()
        if not first:
            self.db.set_setting("float_text_1", hint)
        elif first != hint and not second:
            self.db.set_setting("float_text_2", hint)
        self.db.set_setting("float_hint_v350_seeded", "1")

    def _ensure_v37_float_hint_copy(self) -> None:
        """Shorten only the former built-in double-click wording on upgrade."""
        if self.db.get_setting("float_hint_v370_copy_updated", "0") == "1":
            return
        old_hint = "双击浮窗内容可打开主页面"
        new_hint = "双击浮窗可打开主页面"
        for slot in range(1, 4):
            key = f"float_text_{slot}"
            if self.db.get_setting(key, "").strip() == old_hint:
                self.db.set_setting(key, new_hint)
        self.db.set_setting("float_hint_v370_copy_updated", "1")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)

        header_panel = QFrame()
        header_panel.setObjectName("chromePanel")
        header_outer = QVBoxLayout(header_panel)
        header_outer.setContentsMargins(16, 13, 16, 11)
        header_outer.setSpacing(7)
        header = QHBoxLayout()
        title = QLabel(f"{APP_NAME} V{APP_VERSION}")
        title.setStyleSheet("font-size:25px; font-weight:600; color:#27364a;")
        self.header_greeting = QLabel()
        self.header_greeting.setWordWrap(True)
        self.header_greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_greeting.setStyleSheet(
            "background:#f1effa; border:1px solid #ddd7ef; border-radius:10px; color:#66527f; "
            "font-size:13px; font-weight:500; padding:6px 10px;"
        )
        header.addWidget(title)
        greeting_column = QVBoxLayout()
        greeting_column.setSpacing(3)
        greeting_column.addWidget(self.header_greeting)
        self.precise_overtime = QLabel()
        self.precise_overtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.precise_overtime.setStyleSheet("font-size:12px; color:#876b43; font-weight:500;")
        greeting_column.addWidget(self.precise_overtime)
        header.addLayout(greeting_column, 1)
        self.float_button = QPushButton("关闭桌面浮窗")
        self.float_button.clicked.connect(self.toggle_float)
        header.addWidget(self.float_button)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        fullscreen = QPushButton("全屏")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        header.addWidget(fullscreen)
        header_outer.addLayout(header)
        details = QHBoxLayout()
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("font-size:13px; color:#7a8491;")
        details.addWidget(self.subtitle)
        details.addStretch()
        header_outer.addLayout(details)
        outer.addWidget(header_panel)

        self.notice = QLabel()
        self.notice.setVisible(False)
        self.notice.setStyleSheet(
            "background:#fff8df; color:#7a5510; border:1px solid #f0dda2; border-radius:9px; padding:8px 10px;"
        )
        outer.addWidget(self.notice)

        toolbar_panel = QFrame()
        toolbar_panel.setObjectName("chromePanel")
        toolbar_outer = QVBoxLayout(toolbar_panel)
        toolbar_outer.setContentsMargins(10, 5, 10, 5)
        toolbar_outer.setSpacing(4)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabBar()
        self.tabs.addTab("当日")
        self.tabs.addTab("未完成")
        self.tabs.addTab("全部")
        self.tabs.setStyleSheet("QTabBar::tab:last { margin-left:18px; }")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        toolbar.addWidget(self.tabs)
        toolbar.addStretch()
        add = QPushButton("+ 添加事项")
        add.setObjectName("primaryButton")
        add.clicked.connect(self.add_task)
        toolbar.addWidget(add)
        toolbar_outer.addLayout(toolbar)

        self.unfinished_filter_row = QWidget()
        unfinished_filters = QHBoxLayout(self.unfinished_filter_row)
        unfinished_filters.setContentsMargins(5, 0, 5, 3)
        unfinished_filters.setSpacing(7)
        filter_label = QLabel("查看日期")
        filter_label.setStyleSheet("font-size:12px; color:#77808c; font-weight:500;")
        unfinished_filters.addWidget(filter_label)
        self.unfinished_date = NoWheelDateEdit(QDate.currentDate())
        self.unfinished_date.setCalendarPopup(True)
        self.unfinished_date.setDisplayFormat("yyyy-MM-dd")
        self.unfinished_date.dateChanged.connect(lambda _: self.render())
        unfinished_filters.addWidget(self.unfinished_date)
        self.all_unfinished = QCheckBox("查看全部未完成")
        self.all_unfinished.toggled.connect(self.render)
        unfinished_filters.addWidget(self.all_unfinished)
        unfinished_filters.addStretch()
        self.unfinished_filter_row.setVisible(False)
        toolbar_outer.addWidget(self.unfinished_filter_row)
        outer.addWidget(toolbar_panel)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 4, 0, 4)
        self.list_layout.setSpacing(5)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_host)
        outer.addWidget(self.scroll, 1)
        self.setStyleSheet(APP_STYLE + """
            QFrame#chromePanel { background:#f4f7fc; border:1px solid #dce6f5; border-radius:14px; }
            QFrame#previewArea { background:#e9ecef; border:1px solid #dde1e5; border-radius:13px; }
        """)

    def on_tab_changed(self, index: int) -> None:
        is_unfinished = index == 1
        self.unfinished_filter_row.setVisible(is_unfinished)
        self.render()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(f"{APP_NAME} V{APP_VERSION}")
        menu = QMenu(self)
        open_action = QAction("打开编辑主窗", self)
        open_action.triggered.connect(self.show_editor)
        menu.addAction(open_action)
        float_action = QAction("显示 / 关闭桌面浮窗", self)
        float_action.triggered.connect(self.toggle_float)
        menu.addAction(float_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_editor() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def clear_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    @staticmethod
    def section_label(text: str, top_padding: int = 12) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"font-size:12px; color:#77808c; font-weight:600; padding:{top_padding}px 2px 3px;")
        return label

    def _offwork_datetime(self, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now()
        try:
            return datetime.strptime(f"{now.date().isoformat()} {self.db.get_setting('off_work_time', '18:10')}", "%Y-%m-%d %H:%M")
        except ValueError:
            logging.warning("Invalid off-work setting")
            return None

    def _setting_list(self, key: str, default: list[str]) -> list[str]:
        try:
            value = json.loads(self.db.get_setting(key, ""))
        except json.JSONDecodeError:
            return list(default)
        return [str(item) for item in value] if isinstance(value, list) else list(default)

    @staticmethod
    def _format_hours(hours: float) -> str:
        return str(int(hours)) if hours.is_integer() else str(hours)

    def _overtime_header(self, now: datetime) -> str:
        # This is a work-computer model: once the configured workday reaches
        # its end time, the header remains in overtime mode until 00:00.  A new
        # calendar day silently starts fresh with the normal encouragement.
        end = self._offwork_datetime(now)
        if not end:
            return ""
        minutes = int((now - end).total_seconds() // 60)
        if minutes < 0:
            return ""
        if minutes < 60:
            return "正在加班\n你今天辛苦啦！"
        hours, remainder = divmod(minutes, 60)
        if remainder < 20:
            shown = float(hours)
        elif remainder < 50:
            shown = hours + 0.5
        else:
            shown = float(hours + 1)
        ending = "夜深了 回家注意安全哦" if shown >= 1.5 else "你今天辛苦啦！"
        return f"加班{self._format_hours(shown)}小时了！\n{ending}"

    def _overtime_reminder_message(self, elapsed_minutes: int) -> str:
        hours = elapsed_minutes / 60
        ending = "夜深了 回家注意安全哦" if hours >= 1.5 else "你今天辛苦啦！"
        return f"加班{self._format_hours(hours)}小时了！\n{ending}"

    @staticmethod
    def _format_precise_overtime(minutes: int) -> str:
        hours, remaining = divmod(minutes, 60)
        if hours and remaining:
            return f"已加班 {hours} 小时 {remaining} 分钟"
        if hours:
            return f"已加班 {hours} 小时"
        return f"已加班 {remaining} 分钟"

    def _editor_brand_message(self, now: datetime) -> str:
        """Choose one non-repeating brand line for each complete clock hour."""
        hour_key = now.strftime("%Y-%m-%d-%H")
        greetings = self.WEEKEND_BRAND_GREETINGS if now.weekday() >= 5 else self.EDITOR_BRAND_GREETINGS
        cached_hour = self.db.get_setting("editor_brand_hour", "")
        cached = self.db.get_setting("editor_brand_message", "")
        if cached_hour == hour_key and cached in greetings:
            return cached
        previous = self.db.get_setting("editor_brand_previous", "")
        choices = [message for message in greetings if message != previous] or list(greetings)
        selected = random.choice(choices)
        self.db.set_setting("editor_brand_hour", hour_key)
        self.db.set_setting("editor_brand_message", selected)
        self.db.set_setting("editor_brand_previous", selected)
        return selected

    def _schedule_next_brand_hour(self) -> None:
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        delay_ms = max(1_000, int((next_hour - now).total_seconds() * 1_000) + 30)
        self.brand_timer.start(delay_ms)

    def _refresh_brand_at_hour(self) -> None:
        self._refresh_header(datetime.now())
        self._schedule_next_brand_hour()

    def _refresh_header(self, now: datetime) -> None:
        self.header_greeting.setText(self._editor_brand_message(now))
        self.subtitle.setText(now.strftime("今天是 %Y 年 %m 月 %d 日"))
        end = self._offwork_datetime(now)
        minutes = int((now - end).total_seconds() // 60) if end else 0
        self.precise_overtime.setText(self._format_precise_overtime(minutes) if minutes >= 30 else "")

    def render(self) -> None:
        self.clear_list()
        now = datetime.now()
        self._refresh_header(now)
        today = self.db.today()
        active_tab = self.tabs.currentIndex()
        showing_all_pending = active_tab == 1 and self.all_unfinished.isChecked()
        if active_tab == 2:
            self._render_all_tasks(self.db.all_tasks())
            self.list_layout.addStretch(1)
            self.refresh_float()
            return
        selected_day = self.unfinished_date.date().toString("yyyy-MM-dd") if active_tab == 1 else today
        tasks = self.db.all_pending_tasks() if showing_all_pending else self.db.tasks_for(
            selected_day, active_tab == 1
        )
        if showing_all_pending:
            self._render_all_pending(tasks)
            self.list_layout.addStretch(1)
            self.refresh_float()
            return
        # Timed pinned tasks join the ordinary chronological flow while retaining
        # their blue pinned background. Untimed pinned tasks live only below.
        normal = [task for task in tasks if not task["is_fixed"] or task["due_time"]]
        normal.sort(key=lambda task: (task["due_time"] is None, task["due_time"] or "", task["created_at"]))
        fixed = [task for task in tasks if task["is_fixed"]]
        if normal:
            section_title = "今日事项" if active_tab == 0 else f"{selected_day} · 未完成"
            self.list_layout.addWidget(self.section_label(section_title))
            for task in normal:
                self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))
        else:
            empty_text = "今天还没有事项。点击右上角“添加事项”开始安排。" if active_tab == 0 else "这一天没有未完成事项。"
            empty = QLabel(empty_text)
            empty.setStyleSheet("color:#87909c; padding:28px 6px;")
            self.list_layout.addWidget(empty)
        if fixed:
            fixed_label = self.section_label("固定待办", 0)
            fixed_label.setFixedHeight(16)
            self.list_layout.addWidget(fixed_label)
            for task in fixed:
                self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))
        if active_tab == 0:
            tomorrow = (now + timedelta(days=1)).date().isoformat()
            tomorrow_tasks = self.db.tasks_for(tomorrow)
            preview = [task for task in tomorrow_tasks if not task["is_fixed"]][:2]
            preview += [task for task in tomorrow_tasks if task["is_fixed"]][:2]
            if preview:
                self.list_layout.addSpacing(30)
                preview_host = QFrame()
                preview_host.setObjectName("previewArea")
                preview_host.setStyleSheet(
                    "QFrame#previewArea {background:#e8eaed; border:1px solid #d9dde2; border-radius:13px;}"
                )
                preview_layout = QVBoxLayout(preview_host)
                preview_layout.setContentsMargins(8, 4, 8, 8)
                preview_layout.setSpacing(7)
                preview_layout.addWidget(self.section_label("明日预览（继续向下滚动查看）", 5))
                for task in preview:
                    preview_layout.addWidget(
                        TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task, preview=True)
                    )
                self.list_layout.addWidget(preview_host)
        self.list_layout.addStretch(1)
        self.refresh_float()

    def _render_all_pending(self, tasks) -> None:
        if not tasks:
            empty = QLabel("暂无未完成事项。")
            empty.setStyleSheet("color:#87909c; padding:28px 6px;")
            self.list_layout.addWidget(empty)
            return
        current_date = None
        for task in tasks:
            if task["task_date"] != current_date:
                current_date = task["task_date"]
                self.list_layout.addWidget(self.section_label(f"{current_date} · 未完成"))
            self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))

    def _render_all_tasks(self, tasks) -> None:
        if not tasks:
            empty = QLabel("还没有保存的事项。")
            empty.setStyleSheet("color:#87909c; padding:28px 6px;")
            self.list_layout.addWidget(empty)
            return
        current_date = None
        for task in tasks:
            if task["task_date"] != current_date:
                current_date = task["task_date"]
                self.list_layout.addWidget(self.section_label(f"{current_date} · 全部事项"))
            self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))

    @staticmethod
    def _is_past_due(values: dict) -> bool:
        due_time = values.get("due_time")
        task_date = values.get("task_date")
        if not due_time or not task_date:
            return False
        try:
            return datetime.strptime(f"{task_date} {due_time}", "%Y-%m-%d %H:%M") <= datetime.now()
        except (TypeError, ValueError):
            return False

    def _skip_historical_alerts_if_needed(self, task_id: int, values: dict) -> None:
        """Past-due items remain unfinished and overdue, but never replay alerts."""
        if self._is_past_due(values):
            self.db.mark_alerted(task_id, "pre")
            self.db.mark_alerted(task_id, "due")

    def add_task(self) -> None:
        dialog = TaskDialog(parent=self)
        if self._run_passive_float_dialog(dialog) == QDialog.DialogCode.Accepted:
            values = dialog.values()
            task_id = self.db.add_task(**values)
            self._skip_historical_alerts_if_needed(task_id, values)
            self.render()

    def edit_task(self, task) -> None:
        dialog = TaskDialog(task, self)
        if self._run_passive_float_dialog(dialog) == QDialog.DialogCode.Accepted:
            values = dialog.values()
            if dialog.duplicate_requested():
                task_id = self.db.add_task(**values)
            else:
                self.db.update_task(task["id"], **values)
                task_id = task["id"]
            self._skip_historical_alerts_if_needed(task_id, values)
            self.render()

    def set_completed(self, task_id: int, completed: bool) -> None:
        self.db.set_completed(task_id, completed)
        self.render()

    def delete_task(self, task) -> None:
        if QMessageBox.question(self, "删除事项", "确定删除这条事项吗？") == QMessageBox.StandardButton.Yes:
            self.db.delete_task(task["id"])
            self.render()

    def open_float_menu(self, task) -> None:
        menu = QMenu(self)
        manual_count = int(self.db.get_setting("manual_float_count", "3"))
        occupied = {item["float_slot"]: item for item in self.db.float_tasks()}
        for slot in range(1, manual_count + 1):
            other = occupied.get(slot)
            suffix = f"（替换：{other['title']}）" if other and other["id"] != task["id"] else ""
            action = QAction(f"钉到桌边重点位 {slot}{suffix}", self)
            action.triggered.connect(lambda _, number=slot: self.assign_float_task(task["id"], number))
            menu.addAction(action)
        # The task card may have been rendered before another menu action or a
        # refresh changed its slot.  Consult the database for the authoritative
        # state so a truly pinned item can always be removed, while an ordinary
        # item never gains a misleading removal action.
        current_task = self.db.task_by_id(task["id"])
        if current_task and current_task["float_slot"] is not None:
            remove = QAction("移出桌边重点位（取消钉住）", self)
            remove.triggered.connect(lambda: (self.db.update_task(task["id"], float_slot=None), self.refresh_float()))
            menu.addAction(remove)
        menu.exec(self.cursor().pos())

    def assign_float_task(self, task_id: int, slot: int) -> None:
        occupied = next((item for item in self.db.float_tasks() if item["float_slot"] == slot and item["id"] != task_id), None)
        if occupied and QMessageBox.question(self, "替换浮窗内容", f"位置 {slot} 当前是“{occupied['title']}”。确定替换吗？") != QMessageBox.StandardButton.Yes:
            return
        self.db.clear_float_slot(slot)
        self.db.update_task(task_id, float_slot=slot)
        self.refresh_float()

    @staticmethod
    def _deduplicate_countdown_tasks(tasks, highlighted_ids: set[int]):
        """Keep one float card for identical copied items, preferring an alerting copy."""
        unique = []
        indexes: dict[tuple[str, str], int] = {}
        for task in tasks:
            key = (task["due_time"], task["title"])
            if key not in indexes:
                indexes[key] = len(unique)
                unique.append(task)
            elif task["id"] in highlighted_ids:
                unique[indexes[key]] = task
        return unique

    @staticmethod
    def _countdown_cards(timed_tasks, untimed_tasks, count: int):
        """Keep timed work at the top; use untimed work to fill bottom slots.

        A task without a precise time is not a countdown item, so it must not
        displace a timed item or jump to the top. When the countdown has room,
        it becomes a gentle fallback at the bottom of the float.
        """
        timed = list(timed_tasks[:count])
        remaining = count - len(timed)
        untimed = list(untimed_tasks[:remaining])
        empty = [("", "", -1, "empty")] * (remaining - len(untimed))
        timed_cards = [(task["due_time"], task["title"], task["id"], "task") for task in timed]
        untimed_cards = [("", task["title"], task["id"], "task") for task in untimed]
        return timed_cards + empty + untimed_cards

    def refresh_float(self, countdown_count: int | None = None, manual_count: int | None = None) -> None:
        now = datetime.now()
        countdown_count = countdown_count if countdown_count is not None else int(self.db.get_setting("countdown_float_count", "3"))
        manual_count = manual_count if manual_count is not None else int(self.db.get_setting("manual_float_count", "3"))
        greeting = self.db.get_setting("float_greeting", self.DEFAULT_GREETINGS[0])
        auto_collapse_delay = self.db.get_setting("float_auto_collapse", "4")
        self.float_window.configure(
            greeting,
            countdown_count,
            manual_count,
            self._overtime_header(now),
            auto_collapse_delay,
        )
        scheduled = [task for task in self.db.tasks_for(self.db.today(), pending_only=True) if task["due_time"]]
        past, future = [], []
        for task in scheduled:
            due = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
            (past if due <= now else future).append((due, task))
        visible = [task for _, task in sorted(past, reverse=True, key=lambda pair: pair[0]) if task["id"] in self.alert_task_ids]
        visible.extend(task for _, task in sorted(future, key=lambda pair: pair[0]))
        # A copied task is intentionally a separate editor record. If its title
        # and due time are still identical, show only one automatic countdown
        # card so the compact float is not consumed by duplicates.
        visible = self._deduplicate_countdown_tasks(visible, self.alert_task_ids)
        # Untimed work is a fallback only. It stays in the lowest available
        # countdown positions, preserving the list order instead of competing
        # with the time-based items above it.
        untimed = [
            task for task in self.db.tasks_for(self.db.today(), pending_only=True)
            if not task["due_time"]
        ]
        countdown = self._countdown_cards(visible, untimed, countdown_count)
        fixed = {task["float_slot"]: task for task in self.db.float_tasks()}
        manual = []
        for slot in range(1, manual_count + 1):
            task = fixed.get(slot)
            text = task["title"] if task else self.db.get_setting(f"float_text_{slot}", "")
            source = "task" if task else ("fixed_text" if text else "empty")
            manual.append((str(slot), text, source))
        self.float_window.set_items(countdown, manual, self.alert_task_ids)

    def float_is_enabled(self) -> bool:
        return self.db.get_setting("float_enabled", "1") == "1"

    def restore_float(self) -> None:
        if not self.float_is_enabled():
            self.float_button.setText("显示桌面浮窗")
            return
        self.float_window.dock_to_right(collapsed=True)
        self.float_window.show()
        self.float_button.setText("关闭桌面浮窗")

    def toggle_float(self) -> None:
        if self.float_is_enabled():
            self.db.set_setting("float_enabled", "0")
            self.alert_task_ids.clear()
            self.float_window.hide()
            self.float_button.setText("显示桌面浮窗")
            self.refresh_float()
        else:
            self.db.set_setting("float_enabled", "1")
            self.float_window.dock_to_right(collapsed=False)
            self.float_window.show()
            self.float_window.expand()
            self.float_button.setText("关闭桌面浮窗")

    def save_float_position(self, y: int) -> None:
        self.db.set_setting("float_dock_y", str(y))

    def set_hotkey_manager(self, manager) -> None:
        self.hotkey_manager = manager

    def apply_shortcut(self, shortcut: str) -> bool:
        return shortcut == "none" if self.hotkey_manager is None else self.hotkey_manager.register(shortcut)

    def show_editor(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.render()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        QTimer.singleShot(10_000, lambda: self.notice.setVisible(False))

    def _trigger_float(self, message: str = "", *, reminder_kind: str = "task") -> None:
        if self.float_is_enabled():
            overtime_active = bool(self._overtime_header(datetime.now()))
            # Once overtime starts, the float header remains the overtime status.
            # Other reminder types may still expand the float but cannot replace it.
            if overtime_active and message and reminder_kind != "overtime":
                self.float_window.show_alert()
            else:
                self.float_window.show_alert(message)

    def _check_lifestyle_reminders(self, now: datetime) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = []
        end = self._offwork_datetime(now)
        today = now.date().isoformat()

        if self.db.get_setting("water_enabled", "1") == "1":
            custom = [value for value in self._setting_list("water_custom_times", ["", "", ""]) if value]
            fixed = self._setting_list("water_fixed_times", ["10:15", "15:15"])
            water_times = list(dict.fromkeys([*fixed, *custom]))
            for value in water_times:
                key = f"water_reminded_{today}_{value}"
                try:
                    target = datetime.strptime(f"{today} {value}", "%Y-%m-%d %H:%M")
                except ValueError:
                    logging.warning("Invalid water reminder time: %s", value)
                    continue
                elapsed = (now - target).total_seconds()
                if 0 <= elapsed <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    if value == "15:15":
                        messages.append(("water", "下午三点，饮茶了先！\n你辛苦啦！"))
                    else:
                        messages.append(("water", "喝水时间到了\n你辛苦啦！"))

        if self.db.get_setting("eye_enabled", "1") == "1":
            custom = [value for value in self._setting_list("eye_custom_times", ["", "", ""]) if value]
            fixed = self._setting_list("eye_fixed_times", ["11:35", "16:40"])
            eye_times = list(dict.fromkeys([*fixed, *custom]))
            for value in eye_times:
                key = f"eye_reminded_{today}_{value}"
                try:
                    target = datetime.strptime(f"{today} {value}", "%Y-%m-%d %H:%M")
                except ValueError:
                    logging.warning("Invalid eye reminder time: %s", value)
                    continue
                elapsed = (now - target).total_seconds()
                if 0 <= elapsed <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append(("eye", "眼睛和你都辛苦啦\n闭上眼 按摩休息一下吧"))

        if self.db.get_setting("meal_enabled", "0") == "1":
            for value in self._setting_list("meal_times", ["11:59", "17:59"]):
                key = f"meal_reminded_{today}_{value}"
                try:
                    target = datetime.strptime(f"{today} {value}", "%Y-%m-%d %H:%M")
                except ValueError:
                    logging.warning("Invalid meal reminder time: %s", value)
                    continue
                elapsed = (now - target).total_seconds()
                if 0 <= elapsed <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append(("meal", "马上就吃饭啦\n你今天辛苦啦！"))

        if end and self.db.get_setting("offwork_enabled", "0") == "1":
            leads = self._setting_list(
                "offwork_lead_minutes_list", [self.db.get_setting("offwork_lead_minutes", "5")]
            )
            seconds = (end - now).total_seconds()
            for raw_lead in leads:
                try:
                    lead = int(raw_lead)
                except ValueError:
                    continue
                key = f"offwork_reminded_{today}_{lead}"
                if 0 < seconds <= lead * 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append(("offwork", f"还有 {lead} 分钟下班了\n你今天辛苦啦！"))

        if end and self.db.get_setting("overtime_enabled", "1") == "1":
            cadence = int(self.db.get_setting("overtime_cadence", "30"))
            elapsed = int((now - end).total_seconds())
            if elapsed >= cadence * 60:
                count = elapsed // (cadence * 60)
                remainder = elapsed % (cadence * 60)
                key = f"overtime_reminded_{today}_{count}_{cadence}"
                if remainder <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append(("overtime", self._overtime_reminder_message(count * cadence)))
        return [(kind, message) for kind, message in messages if message]

    def check_reminders(self) -> None:
        now = datetime.now()
        if self.isVisible():
            self._refresh_header(now)
        task_alerts: set[int] = set()
        for task in self.db.tasks_needing_reminder(self.db.today()):
            due = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
            seconds = (due - now).total_seconds()
            if 0 < seconds <= 600 and not task["pre_alerted_at"]:
                self.db.mark_alerted(task["id"], "pre")
                task_alerts.add(task["id"])
            elif seconds <= 0 and not task["due_alerted_at"]:
                self.db.mark_alerted(task["id"], "due")
                task_alerts.add(task["id"])
        if task_alerts and self.float_is_enabled():
            self.alert_task_ids.update(task_alerts)
            self.refresh_float()
            self._trigger_float()
            if self.isVisible():
                self.show_notice("提醒事项已在桌面浮窗高亮显示")
        else:
            self.refresh_float()
        lifestyle = self._check_lifestyle_reminders(now)
        if lifestyle:
            reminder_kind, message = lifestyle[-1]
            self._trigger_float(message, reminder_kind=reminder_kind)
            if self.isVisible():
                self.show_notice(message)

    def finish_float_alert(self) -> None:
        self.alert_task_ids.clear()
        self.refresh_float()
        self.render()

    def _run_passive_float_dialog(self, dialog: QDialog) -> QDialog.DialogCode:
        """Keep the main page modal while the separate desktop float observes.

        The float may still expand under the mouse and receive an alert, but it
        cannot be dragged, collapsed or double-clicked until this dialog closes.
        """
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.float_window.set_passive_mode(True)
        try:
            return dialog.exec()
        finally:
            self.float_window.set_passive_mode(False)

    def open_settings(self) -> None:
        try:
            greetings = json.loads(self.db.get_setting("saved_float_greetings", ""))
            if not isinstance(greetings, list):
                greetings = []
        except json.JSONDecodeError:
            greetings = []
        greetings = [text for text in greetings if isinstance(text, str) and text.strip()]
        dialog = SettingsDialog(self.db, greetings, self)
        dialog.countdown_count.valueChanged.connect(
            lambda value: self.refresh_float(value, dialog.manual_count.value())
        )
        dialog.manual_count.valueChanged.connect(
            lambda value: self.refresh_float(dialog.countdown_count.value(), value)
        )
        dialog.collapse_delay.currentIndexChanged.connect(
            lambda _: self.float_window.set_auto_collapse_delay(dialog.collapse_delay.currentData())
        )
        if self._run_passive_float_dialog(dialog) == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.db.set_setting("off_work_time", values["off_work_time"])
            self.db.set_setting("autostart", "1" if values["autostart"] else "0")
            self.db.set_setting("water_enabled", "1" if values["water_enabled"] else "0")
            self.db.set_setting("water_fixed_times", json.dumps(values["water_fixed_times"]))
            self.db.set_setting("water_custom_times", json.dumps(values["water_custom_times"]))
            self.db.set_setting("eye_enabled", "1" if values["eye_enabled"] else "0")
            self.db.set_setting("eye_fixed_times", json.dumps(values["eye_fixed_times"]))
            self.db.set_setting("eye_custom_times", json.dumps(values["eye_custom_times"]))
            self.db.set_setting("meal_enabled", "1" if values["meal_enabled"] else "0")
            self.db.set_setting("meal_times", json.dumps(values["meal_times"]))
            self.db.set_setting("offwork_enabled", "1" if values["offwork_enabled"] else "0")
            self.db.set_setting("offwork_lead_minutes_list", json.dumps(values["offwork_leads"]))
            self.db.set_setting("offwork_lead_minutes", str(values["offwork_leads"][0] if values["offwork_leads"] else 5))
            self.db.set_setting("overtime_enabled", "1" if values["overtime_enabled"] else "0")
            self.db.set_setting("overtime_cadence", str(values["overtime_cadence"]))
            self.db.set_setting("saved_float_greetings", json.dumps(values["greetings"], ensure_ascii=False))
            self.db.set_setting("float_greeting", values["greeting"])
            self.db.set_setting("countdown_float_count", str(values["countdown_count"]))
            self.db.set_setting("manual_float_count", str(values["manual_count"]))
            self.db.set_setting("float_auto_collapse", str(values["collapse_delay"]))
            self.db.set_setting("float_shortcut", str(values["shortcut"]))
            for slot, text in values["fixed_texts"].items():
                self.db.set_setting(f"float_text_{slot}", text)
            self.set_autostart(values["autostart"])
            if self.hotkey_manager and values["shortcut"] == "none":
                self.hotkey_manager.unregister()
            elif values["shortcut"] != "none" and not self.apply_shortcut(values["shortcut"]):
                self.show_notice("Alt + E 未能启用，可能正被其他软件占用。")
            self.render()
        else:
            self.render()

    def set_autostart(self, enabled: bool) -> None:
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, "DaKeDesk", 0, winreg.REG_SZ, f'"{sys.executable}" --background')
                    try:
                        winreg.DeleteValue(key, "WorkTodo")
                    except FileNotFoundError:
                        pass
                else:
                    for value_name in ("DaKeDesk", "WorkTodo"):
                        try:
                            winreg.DeleteValue(key, value_name)
                        except FileNotFoundError:
                            pass
        except OSError:
            logging.exception("Could not update Windows auto-start setting")

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def quit_app(self) -> None:
        self.float_window.hide()
        self.tray.hide()
        self.db.close()
        QApplication.quit()
