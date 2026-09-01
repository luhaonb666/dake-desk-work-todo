"""The editable Work Todo window and its compact desktop float panel."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta

from PyQt6.QtCore import QDate, QTime, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSystemTrayIcon, QTabBar, QTimeEdit,
    QVBoxLayout, QWidget,
)

from app_paths import app_data_dir
from storage.database import Database
from ui.float_window import FloatWindow
from ui.task_dialog import TaskDialog


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
    def __init__(self, task, on_complete, on_edit, on_float, on_delete, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("taskCard")
        overdue = bool(task["due_time"] and not task["is_completed"] and datetime.strptime(
            f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M"
        ) < datetime.now())
        color, border = ("#edf3ff", "#bcd0f7") if task["is_fixed"] else (
            ("#fff1f1", "#efc4c4") if overdue else ("#ffffff", "#e5e8ec")
        )
        self.setStyleSheet(f"QFrame#taskCard {{background:{color}; border:1px solid {border}; border-radius:12px;}}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)
        check = QCheckBox()
        check.setChecked(bool(task["is_completed"]))
        check.toggled.connect(lambda checked: on_complete(task["id"], checked))
        layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        content = QVBoxLayout()
        heading = f"{task['due_time']}  {task['title']}" if task["due_time"] else task["title"]
        title = QLabel(heading)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:15px; font-weight:600; color:#8c939d; text-decoration:line-through;"
            if task["is_completed"] else "font-size:15px; font-weight:600; color:#26313e;"
        )
        content.addWidget(title)
        if task["notes"]:
            notes = QLabel(task["notes"])
            notes.setWordWrap(True)
            notes.setStyleSheet("font-size:12px; color:#718096; margin-top:2px;")
            content.addWidget(notes)
        if overdue:
            warning = QLabel("已超时")
            warning.setStyleSheet("font-size:12px; color:#bd5b5b; margin-top:2px;")
            content.addWidget(warning)
        layout.addLayout(content, 1)
        for text, callback in (("编辑", lambda: on_edit(task)), ("浮窗", lambda: on_float(task)), ("删除", lambda: on_delete(task))):
            button = QPushButton(text)
            button.setObjectName("quietButton")
            button.clicked.connect(callback)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)


class MainWindow(QMainWindow):
    DEFAULT_GREETINGS = [
        "工作辛苦，也要保持开心鸭！",
        "慢慢推进，今天也很棒！",
        "稳稳完成眼前这一件就好。",
        "我为亚泰添砖加瓦",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.db = Database(app_data_dir() / "work-todo.db")
        self.db.ensure_settings_table()
        self.setWindowTitle("工作待办 V1.4")
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
        self.render()
        QTimer.singleShot(250, self.restore_float)
        QTimer.singleShot(1_000, self.check_reminders)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("工作待办 V1.4")
        title.setStyleSheet("font-size:26px; font-weight:700; color:#1f2937;")
        self.header_greeting = QLabel()
        self.header_greeting.setWordWrap(True)
        self.header_greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_greeting.setStyleSheet(
            "background:#f1edf9; border:1px solid #ded4ed; border-radius:10px; color:#66527f; "
            "font-size:13px; font-weight:600; padding:5px 9px;"
        )
        header.addWidget(title)
        greeting_column = QVBoxLayout()
        greeting_column.setSpacing(3)
        greeting_column.addWidget(self.header_greeting)
        self.precise_overtime = QLabel()
        self.precise_overtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.precise_overtime.setStyleSheet("font-size:12px; color:#876b43; font-weight:600;")
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
        outer.addLayout(header)
        details = QHBoxLayout()
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("font-size:13px; color:#7a8491;")
        details.addWidget(self.subtitle)
        details.addStretch()
        outer.addLayout(details)
        self.notice = QLabel()
        self.notice.setVisible(False)
        self.notice.setStyleSheet("background:#fff5d8; color:#7a5510; border-radius:8px; padding:8px 10px;")
        outer.addWidget(self.notice)
        toolbar = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.addTab("全部")
        self.tabs.addTab("未完成")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        toolbar.addWidget(self.tabs)
        self.unfinished_date = QDateEdit(QDate.currentDate())
        self.unfinished_date.setCalendarPopup(True)
        self.unfinished_date.setDisplayFormat("yyyy-MM-dd")
        self.unfinished_date.dateChanged.connect(lambda _: self.render())
        self.unfinished_date.setVisible(False)
        toolbar.addWidget(self.unfinished_date)
        self.all_unfinished = QCheckBox("全部未完成")
        self.all_unfinished.toggled.connect(self.render)
        self.all_unfinished.setVisible(False)
        toolbar.addWidget(self.all_unfinished)
        toolbar.addStretch()
        add = QPushButton("+ 添加事项")
        add.setObjectName("primaryButton")
        add.clicked.connect(self.add_task)
        toolbar.addWidget(add)
        outer.addLayout(toolbar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 4, 0, 4)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_host)
        outer.addWidget(self.scroll, 1)
        self.setStyleSheet("""
            QWidget#root { background:#fbf9ff; }
            QPushButton { background:#ffffff; border:1px solid #e6dfef; border-radius:12px; padding:7px 11px; color:#514c61; }
            QPushButton:hover { background:#f4efff; }
            QPushButton#primaryButton { background:#9f86d9; color:white; border:none; font-weight:600; }
            QPushButton#primaryButton:hover { background:#8b70cb; }
            QPushButton#quietButton { border:none; background:transparent; color:#718096; padding:3px 5px; font-size:12px; }
            QTabBar::tab { background:transparent; color:#77808c; padding:8px 13px; border-bottom:2px solid transparent; }
            QTabBar::tab:selected { color:#315fc9; border-bottom:2px solid #4f7cff; font-weight:600; }
        """)

    def on_tab_changed(self, index: int) -> None:
        is_unfinished = index == 1
        self.unfinished_date.setVisible(is_unfinished)
        self.all_unfinished.setVisible(is_unfinished)
        self.render()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("工作待办 V1.4")
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
    def section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size:12px; color:#77808c; font-weight:700; padding:12px 2px 3px;")
        return label

    def _offwork_datetime(self, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now()
        try:
            return datetime.strptime(f"{now.date().isoformat()} {self.db.get_setting('off_work_time', '18:10')}", "%Y-%m-%d %H:%M")
        except ValueError:
            logging.warning("Invalid off-work setting")
            return None

    def _overtime_header(self, now: datetime) -> str:
        end = self._offwork_datetime(now)
        if not end:
            return ""
        minutes = int((now - end).total_seconds() // 60)
        if minutes < 60:
            return ""
        hours, remainder = divmod(minutes, 60)
        if remainder < 20:
            shown = float(hours)
        elif remainder < 50:
            shown = hours + 0.5
        else:
            shown = float(hours + 1)
        amount = str(int(shown)) if shown.is_integer() else str(shown)
        ending = "夜深了回家注意安全！" if shown >= 1.5 else "你辛苦啦！"
        return f"加班 {amount} 小时了，{ending}"

    def _refresh_header(self, now: datetime) -> None:
        greeting = self.db.get_setting("float_greeting", self.DEFAULT_GREETINGS[0])
        self.header_greeting.setText(greeting)
        self.subtitle.setText(now.strftime("今天是 %Y 年 %m 月 %d 日"))
        end = self._offwork_datetime(now)
        minutes = int((now - end).total_seconds() // 60) if end else 0
        self.precise_overtime.setText(f"已加班 {minutes} 分钟" if minutes >= 30 else "")

    def render(self) -> None:
        self.clear_list()
        now = datetime.now()
        self._refresh_header(now)
        today = self.db.today()
        showing_all_pending = self.tabs.currentIndex() == 1 and self.all_unfinished.isChecked()
        selected_day = self.unfinished_date.date().toString("yyyy-MM-dd") if self.tabs.currentIndex() == 1 else today
        tasks = self.db.all_pending_tasks() if showing_all_pending else self.db.tasks_for(
            selected_day, self.tabs.currentIndex() == 1
        )
        if showing_all_pending:
            self._render_all_pending(tasks)
            self.list_layout.addStretch(1)
            self.refresh_float()
            return
        # A timed pinned task deliberately appears in both sections: today gives
        # it chronological context, while the second copy keeps it visibly pinned.
        normal = tasks
        fixed = [task for task in tasks if task["is_fixed"]]
        if normal:
            self.list_layout.addWidget(self.section_label("今日事项"))
            for task in normal:
                self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))
        else:
            empty = QLabel("今天还没有事项。点击右上角“添加事项”开始安排。")
            empty.setStyleSheet("color:#87909c; padding:28px 6px;")
            self.list_layout.addWidget(empty)
        if fixed:
            self.list_layout.addWidget(self.section_label("固定待办"))
            for task in fixed:
                self.list_layout.addWidget(TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task))
        if self.tabs.currentIndex() == 0:
            tomorrow = (now + timedelta(days=1)).date().isoformat()
            tomorrow_tasks = self.db.tasks_for(tomorrow)
            preview = [task for task in tomorrow_tasks if not task["is_fixed"]][:2]
            preview += [task for task in tomorrow_tasks if task["is_fixed"]][:2]
            if preview:
                self.list_layout.addWidget(self.section_label("明日预览（继续向下滚动查看）"))
                for task in preview:
                    card = TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task)
                    card.setWindowOpacity(0.78)
                    self.list_layout.addWidget(card)
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

    def add_task(self) -> None:
        dialog = TaskDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.db.add_task(**dialog.values())
            self.render()

    def edit_task(self, task) -> None:
        dialog = TaskDialog(task, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.db.update_task(task["id"], **dialog.values())
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
            action = QAction(f"放入浮窗位置 {slot}{suffix}", self)
            action.triggered.connect(lambda _, number=slot: self.assign_float_task(task["id"], number))
            menu.addAction(action)
        remove = QAction("从浮窗移除", self)
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

    def refresh_float(self, countdown_count: int | None = None, manual_count: int | None = None) -> None:
        now = datetime.now()
        countdown_count = countdown_count if countdown_count is not None else int(self.db.get_setting("countdown_float_count", "3"))
        manual_count = manual_count if manual_count is not None else int(self.db.get_setting("manual_float_count", "3"))
        greeting = self.db.get_setting("float_greeting", self.DEFAULT_GREETINGS[0])
        self.float_window.configure(greeting, countdown_count, manual_count, self._overtime_header(now))
        scheduled = [task for task in self.db.tasks_for(self.db.today(), pending_only=True) if task["due_time"]]
        past, future = [], []
        for task in scheduled:
            due = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
            (past if due <= now else future).append((due, task))
        visible = [task for _, task in sorted(past, reverse=True, key=lambda pair: pair[0]) if task["id"] in self.alert_task_ids]
        visible.extend(task for _, task in sorted(future, key=lambda pair: pair[0]))
        countdown = [(task["due_time"], task["title"], task["id"]) for task in visible[:countdown_count]]
        countdown.extend([("", "", -1)] * (countdown_count - len(countdown)))
        fixed = {task["float_slot"]: task for task in self.db.float_tasks()}
        manual = []
        for slot in range(1, manual_count + 1):
            task = fixed.get(slot)
            text = task["title"] if task else self.db.get_setting(f"float_text_{slot}", "")
            manual.append((str(slot), text))
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

    def _trigger_float(self, message: str = "") -> None:
        if self.float_is_enabled():
            self.float_window.show_alert(message)

    def _check_lifestyle_reminders(self, now: datetime) -> list[str]:
        messages: list[str] = []
        end = self._offwork_datetime(now)
        if not end:
            return messages
        today = now.date().isoformat()
        if self.db.get_setting("offwork_enabled", "1") == "1":
            lead = int(self.db.get_setting("offwork_lead_minutes", "5"))
            key = f"offwork_reminded_{today}"
            seconds = (end - now).total_seconds()
            if 0 < seconds <= lead * 60 and not self.db.get_setting(key):
                self.db.set_setting(key, "1")
                messages.append(f"还有 {lead} 分钟下班了，你辛苦啦！")
        if self.db.get_setting("water_enabled", "1") == "1":
            for value in ("10:15", "15:15"):
                key = f"water_reminded_{today}_{value}"
                target = datetime.strptime(f"{today} {value}", "%Y-%m-%d %H:%M")
                elapsed = (now - target).total_seconds()
                if 0 <= elapsed <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append("喝水时间到啦，你辛苦啦！")
        if self.db.get_setting("overtime_enabled", "1") == "1":
            cadence = int(self.db.get_setting("overtime_cadence", "60"))
            elapsed = int((now - end).total_seconds())
            if elapsed >= cadence * 60:
                count = elapsed // (cadence * 60)
                remainder = elapsed % (cadence * 60)
                key = f"overtime_reminded_{today}_{count}_{cadence}"
                if remainder <= 60 and not self.db.get_setting(key):
                    self.db.set_setting(key, "1")
                    messages.append(self._overtime_header(now))
        return [message for message in messages if message]

    def check_reminders(self) -> None:
        now = datetime.now()
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
            self._trigger_float(lifestyle[-1])
            if self.isVisible():
                self.show_notice(lifestyle[-1])

    def finish_float_alert(self) -> None:
        self.alert_task_ids.clear()
        self.refresh_float()
        self.render()

    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("设置")
        dialog.setMinimumWidth(530)
        form = QFormLayout(dialog)
        end_time = QTimeEdit()
        end_time.setDisplayFormat("HH:mm")
        end_time.setTime(QTime.fromString(self.db.get_setting("off_work_time", "18:10"), "HH:mm"))
        autostart = QCheckBox("开机后在后台启动")
        autostart.setChecked(self.db.get_setting("autostart", "1") == "1")
        offwork_enabled = QCheckBox("开启下班提醒")
        offwork_enabled.setChecked(self.db.get_setting("offwork_enabled", "1") == "1")
        offwork_lead = QComboBox()
        for minutes in (1, 5, 10, 15):
            offwork_lead.addItem(f"下班前 {minutes} 分钟", str(minutes))
        offwork_lead.setCurrentIndex(max(0, offwork_lead.findData(self.db.get_setting("offwork_lead_minutes", "5"))))
        water_enabled = QCheckBox("开启喝水提醒（10:15、15:15）")
        water_enabled.setChecked(self.db.get_setting("water_enabled", "1") == "1")
        overtime_enabled = QCheckBox("开启加班提醒")
        overtime_enabled.setChecked(self.db.get_setting("overtime_enabled", "1") == "1")
        overtime_cadence = QComboBox()
        overtime_cadence.addItem("每 1 小时提醒（默认）", "60")
        overtime_cadence.addItem("每半小时提醒", "30")
        overtime_cadence.setCurrentIndex(max(0, overtime_cadence.findData(self.db.get_setting("overtime_cadence", "60"))))
        countdown_count = QSpinBox()
        countdown_count.setRange(3, 5)
        countdown_count.setValue(int(self.db.get_setting("countdown_float_count", "3")))
        manual_count = QSpinBox()
        manual_count.setRange(0, 4)
        manual_count.setValue(int(self.db.get_setting("manual_float_count", "3")))
        shortcut = QComboBox()
        shortcut.addItem("无快捷键", "none")
        shortcut.addItem("Alt + E（建议）", "alt+e")
        shortcut.setCurrentIndex(1 if self.db.get_setting("float_shortcut", "none") == "alt+e" else 0)
        try:
            greetings = json.loads(self.db.get_setting("saved_float_greetings", ""))
            if not isinstance(greetings, list):
                greetings = []
        except json.JSONDecodeError:
            greetings = []
        greetings = [text for text in greetings if isinstance(text, str) and text.strip()] or self.DEFAULT_GREETINGS.copy()
        greeting = QComboBox()
        greeting.setEditable(True)
        greeting.addItems(greetings)
        saved_greeting = self.db.get_setting("float_greeting", greetings[0])
        greeting.setCurrentText(saved_greeting)
        delete_greeting = QPushButton("删除当前鼓励语")
        def remove_greeting() -> None:
            index = greeting.currentIndex()
            if index >= 0:
                greeting.removeItem(index)
        delete_greeting.clicked.connect(remove_greeting)
        greeting_box = QHBoxLayout()
        greeting_box.setContentsMargins(0, 0, 0, 0)
        greeting_box.addWidget(greeting, 1)
        greeting_box.addWidget(delete_greeting)
        fixed_texts = []
        for slot in range(1, 4):
            edit = QLineEdit(self.db.get_setting(f"float_text_{slot}", ""))
            edit.setPlaceholderText("没有指定事项时显示的固定文字")
            fixed_texts.append((slot, edit))
        form.addRow("下班时间", end_time)
        form.addRow("", autostart)
        form.addRow("", offwork_enabled)
        form.addRow("下班提醒时间", offwork_lead)
        form.addRow("", water_enabled)
        form.addRow("", overtime_enabled)
        form.addRow("加班提醒频率", overtime_cadence)
        form.addRow("顶部鼓励语", greeting_box)
        form.addRow("倒计时待办数量", countdown_count)
        form.addRow("手动固定浮窗位数量", manual_count)
        form.addRow("弹出快捷键", shortcut)
        for slot, edit in fixed_texts:
            form.addRow(f"浮窗位置 {slot} 固定文字", edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        countdown_count.valueChanged.connect(lambda value: self.refresh_float(value, manual_count.value()))
        manual_count.valueChanged.connect(lambda value: self.refresh_float(countdown_count.value(), value))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            chosen = greeting.currentText().strip()
            values = [greeting.itemText(index).strip() for index in range(greeting.count()) if greeting.itemText(index).strip()]
            if chosen and chosen not in values:
                values.append(chosen)
            chosen = chosen if chosen in values else (values[0] if values else "")
            self.db.set_setting("off_work_time", end_time.time().toString("HH:mm"))
            self.db.set_setting("autostart", "1" if autostart.isChecked() else "0")
            self.db.set_setting("offwork_enabled", "1" if offwork_enabled.isChecked() else "0")
            self.db.set_setting("offwork_lead_minutes", offwork_lead.currentData())
            self.db.set_setting("water_enabled", "1" if water_enabled.isChecked() else "0")
            self.db.set_setting("overtime_enabled", "1" if overtime_enabled.isChecked() else "0")
            self.db.set_setting("overtime_cadence", overtime_cadence.currentData())
            self.db.set_setting("saved_float_greetings", json.dumps(values, ensure_ascii=False))
            self.db.set_setting("float_greeting", chosen)
            self.db.set_setting("countdown_float_count", str(countdown_count.value()))
            self.db.set_setting("manual_float_count", str(manual_count.value()))
            self.db.set_setting("float_shortcut", shortcut.currentData())
            for slot, edit in fixed_texts:
                self.db.set_setting(f"float_text_{slot}", edit.text().strip())
            self.set_autostart(autostart.isChecked())
            if shortcut.currentData() != "none" and not self.apply_shortcut(shortcut.currentData()):
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
                    winreg.SetValueEx(key, "WorkTodo", 0, winreg.REG_SZ, f'"{sys.executable}" --background')
                else:
                    try:
                        winreg.DeleteValue(key, "WorkTodo")
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
