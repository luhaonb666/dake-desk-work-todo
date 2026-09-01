"""The single editable Work Todo window and its read-only companion float window."""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime, timedelta

from PyQt6.QtCore import QTime, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QTabBar,
    QTimeEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_paths import app_data_dir
from storage.database import Database
from ui.float_window import FloatWindow
from ui.task_dialog import TaskDialog


def app_icon() -> QIcon:
    """Generate a small dependable icon instead of relying on OS theme icons."""
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
        self.task = task
        self.setObjectName("taskCard")
        now = datetime.now()
        overdue = False
        if task["due_time"] and not task["is_completed"]:
            due = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
            overdue = due < now
        if task["is_fixed"]:
            color = "#edf3ff"
            border = "#bcd0f7"
        elif overdue:
            color = "#fff1f1"
            border = "#efc4c4"
        else:
            color = "#ffffff"
            border = "#e5e8ec"
        self.setStyleSheet(
            f"QFrame#taskCard {{background:{color}; border:1px solid {border}; border-radius:12px;}}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)
        check = QCheckBox()
        check.setChecked(bool(task["is_completed"]))
        check.toggled.connect(lambda checked: on_complete(task["id"], checked))
        layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        text_layout = QVBoxLayout()
        heading = task["title"]
        if task["due_time"]:
            heading = f"{task['due_time']}  {heading}"
        title = QLabel(heading)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:15px; font-weight:600; color:#8c939d; text-decoration:line-through;"
            if task["is_completed"]
            else "font-size:15px; font-weight:600; color:#26313e;"
        )
        text_layout.addWidget(title)
        if task["notes"]:
            notes = QLabel(task["notes"])
            notes.setWordWrap(True)
            notes.setStyleSheet("font-size:12px; color:#718096; margin-top:2px;")
            text_layout.addWidget(notes)
        if overdue:
            warning = QLabel("已超时")
            warning.setStyleSheet("font-size:12px; color:#bd5b5b; margin-top:2px;")
            text_layout.addWidget(warning)
        layout.addLayout(text_layout, 1)
        edit = QPushButton("编辑")
        edit.setObjectName("quietButton")
        edit.clicked.connect(lambda: on_edit(task))
        layout.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)
        floating = QPushButton("浮窗")
        floating.setObjectName("quietButton")
        floating.clicked.connect(lambda: on_float(task))
        layout.addWidget(floating, 0, Qt.AlignmentFlag.AlignTop)
        delete = QPushButton("删除")
        delete.setObjectName("quietButton")
        delete.clicked.connect(lambda: on_delete(task))
        layout.addWidget(delete, 0, Qt.AlignmentFlag.AlignTop)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db = Database(app_data_dir() / "work-todo.db")
        self.db.ensure_settings_table()
        self.setWindowTitle("工作待办 V1.1")
        self.setWindowIcon(app_icon())
        self.resize(760, 760)
        self.setMinimumSize(570, 520)
        self.float_window = FloatWindow()
        self.float_window.open_requested.connect(self.show_editor)
        self.float_window.collapsed_after_alert.connect(self.finish_float_alert)
        self.float_window.position_changed.connect(self.save_float_position)
        saved_float_y = self.db.get_setting("float_dock_y", "")
        if saved_float_y.isdigit():
            self.float_window.set_dock_y(int(saved_float_y))
        self.alert_task_ids: set[int] = set()
        self.hotkey_manager = None
        self._build_ui()
        self._build_tray()
        self.set_autostart(self.db.get_setting("autostart", "1") == "1")
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(30_000)
        self.render()
        QTimer.singleShot(1_000, self.check_reminders)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("工作待办 V1.1")
        title.setStyleSheet("font-size:26px; font-weight:700; color:#1f2937;")
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("font-size:13px; color:#7a8491;")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box, 1)
        self.float_button = QPushButton("显示桌面浮窗")
        self.float_button.clicked.connect(self.toggle_float)
        header.addWidget(self.float_button)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        fullscreen = QPushButton("全屏")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        header.addWidget(fullscreen)
        outer.addLayout(header)
        self.notice = QLabel()
        self.notice.setVisible(False)
        self.notice.setStyleSheet("background:#fff5d8; color:#7a5510; border-radius:8px; padding:8px 10px;")
        outer.addWidget(self.notice)
        toolbar = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.addTab("全部")
        self.tabs.addTab("未完成")
        self.tabs.currentChanged.connect(lambda _: self.render())
        toolbar.addWidget(self.tabs)
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
        self.setStyleSheet(
            """
            QWidget#root { background:#fbf9ff; }
            QPushButton { background:#ffffff; border:1px solid #e6dfef; border-radius:12px; padding:7px 11px; color:#514c61; }
            QPushButton:hover { background:#f4efff; }
            QPushButton#primaryButton { background:#9f86d9; color:white; border:none; font-weight:600; }
            QPushButton#primaryButton:hover { background:#8b70cb; }
            QPushButton#quietButton { border:none; background:transparent; color:#718096; padding:3px 5px; font-size:12px; }
            QTabBar::tab { background:transparent; color:#77808c; padding:8px 13px; border-bottom:2px solid transparent; }
            QTabBar::tab:selected { color:#315fc9; border-bottom:2px solid #4f7cff; font-weight:600; }
            """
        )

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("工作待办")
        menu = QMenu(self)
        open_action = QAction("打开编辑主窗", self)
        open_action.triggered.connect(self.show_editor)
        menu.addAction(open_action)
        float_action = QAction("显示 / 隐藏桌面浮窗", self)
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

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size:12px; color:#77808c; font-weight:700; padding:12px 2px 3px;")
        return label

    def render(self) -> None:
        self.clear_list()
        today = self.db.today()
        self.subtitle.setText(datetime.now().strftime("今天是 %Y 年 %m 月 %d 日"))
        pending_only = self.tabs.currentIndex() == 1
        tasks = self.db.tasks_for(today, pending_only)
        normal = [task for task in tasks if not task["is_fixed"]]
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
        if not pending_only:
            tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
            tomorrow_tasks = self.db.tasks_for(tomorrow)
            preview_normal = [task for task in tomorrow_tasks if not task["is_fixed"]][:2]
            preview_fixed = [task for task in tomorrow_tasks if task["is_fixed"]][:2]
            if preview_normal or preview_fixed:
                self.list_layout.addWidget(self.section_label("明日预览（继续向下滚动查看）"))
                for task in [*preview_normal, *preview_fixed]:
                    preview = TaskCard(task, self.set_completed, self.edit_task, self.open_float_menu, self.delete_task)
                    preview.setWindowOpacity(0.78)
                    self.list_layout.addWidget(preview)
        self.list_layout.addStretch(1)
        self.refresh_float()

    def add_task(self) -> None:
        dialog = TaskDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.db.add_task(**values)
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
        answer = QMessageBox.question(self, "删除事项", "确定删除这条事项吗？")
        if answer == QMessageBox.StandardButton.Yes:
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
        remove.triggered.connect(lambda: self.db.update_task(task["id"], float_slot=None))
        menu.addAction(remove)
        menu.exec(self.cursor().pos())

    def assign_float_task(self, task_id: int, slot: int) -> None:
        occupied = next((item for item in self.db.float_tasks() if item["float_slot"] == slot and item["id"] != task_id), None)
        if occupied:
            answer = QMessageBox.question(self, "替换浮窗内容", f"位置 {slot} 当前是“{occupied['title']}”。确定替换吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.db.clear_float_slot(slot)
        self.db.update_task(task_id, float_slot=slot)
        self.refresh_float()

    def refresh_float(
        self,
        countdown_count: int | None = None,
        manual_count: int | None = None,
    ) -> None:
        today = self.db.today()
        now = datetime.now()
        if countdown_count is None:
            countdown_count = int(self.db.get_setting("countdown_float_count", "3"))
        if manual_count is None:
            manual_count = int(self.db.get_setting("manual_float_count", "3"))
        greeting = self.db.get_setting("float_greeting", "工作辛苦，也要保持开心鸭！")
        self.float_window.configure(greeting, countdown_count, manual_count)
        scheduled = [
            task
            for task in self.db.tasks_for(today, pending_only=True)
            if not task["is_fixed"] and task["due_time"]
        ]
        past = []
        future = []
        for task in scheduled:
            due = datetime.strptime(f"{today} {task['due_time']}", "%Y-%m-%d %H:%M")
            (past if due <= now else future).append((due, task))
        # Overdue tasks remain only while their due-time alert is expanded.
        urgent = [task for _, task in sorted(past, key=lambda pair: pair[0], reverse=True) if task["id"] in self.alert_task_ids]
        urgent.extend(task for _, task in sorted(future, key=lambda pair: pair[0]))
        urgent = urgent[:countdown_count]
        countdown = [(task["due_time"], task["title"], task["id"]) for task in urgent]
        countdown.extend([("", "", -1)] * (countdown_count - len(countdown)))
        custom = {task["float_slot"]: task for task in self.db.float_tasks()}
        manual = []
        for slot in range(1, manual_count + 1):
            task = custom.get(slot)
            text = task["title"] if task else self.db.get_setting(f"float_text_{slot}", "")
            manual.append((str(slot), text))
        self.float_window.set_items(countdown, manual, self.alert_task_ids)

    def toggle_float(self) -> None:
        if self.float_window.isVisible():
            self.float_window.hide()
            self.float_button.setText("显示桌面浮窗")
        else:
            self.float_window.dock_to_right()
            self.float_window.show()
            self.float_window.expand()
            self.float_button.setText("隐藏桌面浮窗")

    def save_float_position(self, y: int) -> None:
        """Remember the vertical placement while preserving the right-edge peek animation."""
        self.db.set_setting("float_dock_y", str(y))

    def set_hotkey_manager(self, manager) -> None:
        self.hotkey_manager = manager

    def apply_shortcut(self, shortcut: str) -> bool:
        if self.hotkey_manager is None:
            return shortcut == "none"
        return self.hotkey_manager.register(shortcut)

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

    def check_reminders(self) -> None:
        now = datetime.now()
        alert_ids: set[int] = set()
        for task in self.db.tasks_needing_reminder(self.db.today()):
            due = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
            seconds = (due - now).total_seconds()
            if 0 < seconds <= 600 and not task["pre_alerted_at"]:
                self.db.mark_alerted(task["id"], "pre")
                alert_ids.add(task["id"])
            elif seconds <= 0 and not task["due_alerted_at"]:
                self.db.mark_alerted(task["id"], "due")
                alert_ids.add(task["id"])
        if alert_ids:
            self.alert_task_ids.update(alert_ids)
            self.refresh_float()
            self.float_window.show_alert()
            if self.isVisible():
                self.show_notice("提醒事项已在桌面浮窗高亮显示")
        else:
            self.refresh_float()
        end_time = self.db.get_setting("off_work_time", "18:00")
        try:
            end = datetime.strptime(f"{self.db.today()} {end_time}", "%Y-%m-%d %H:%M")
            setting_key = f"off_work_reminded_{self.db.today()}"
            if self.isVisible() and 0 < (end - now).total_seconds() <= 600 and not self.db.get_setting(setting_key):
                self.show_notice("提醒：距离下班还有 10 分钟，可以整理今日事项并安排明日。")
                self.db.set_setting(setting_key, "1")
        except ValueError:
            logging.warning("Invalid off-work time setting: %s", end_time)

    def finish_float_alert(self) -> None:
        """Only after the alert panel folds away do due tasks leave its countdown area."""
        self.alert_task_ids.clear()
        self.refresh_float()
        self.render()

    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("设置")
        dialog.setMinimumWidth(500)
        form = QFormLayout(dialog)
        end_time = QTimeEdit()
        end_time.setDisplayFormat("HH:mm")
        end_time.setTime(QTime.fromString(self.db.get_setting("off_work_time", "18:00"), "HH:mm"))
        autostart = QCheckBox("开机后在后台启动")
        autostart.setChecked(self.db.get_setting("autostart", "1") == "1")
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
        greetings = ["工作辛苦，也要保持开心鸭！", "慢慢推进，今天也很棒！", "稳稳完成眼前这一件就好。"]
        try:
            saved_greetings = json.loads(self.db.get_setting("saved_float_greetings", "[]"))
        except json.JSONDecodeError:
            saved_greetings = []
        greeting = QComboBox()
        greeting.setEditable(True)
        greeting.addItems([*greetings, *[text for text in saved_greetings if text not in greetings]])
        saved_greeting = self.db.get_setting("float_greeting", greetings[0])
        if greeting.findText(saved_greeting) < 0:
            greeting.addItem(saved_greeting)
        greeting.setCurrentText(saved_greeting)
        encouragement = []
        for slot in range(1, 5):
            edit = QLineEdit(self.db.get_setting(f"float_text_{slot}", ""))
            edit.setPlaceholderText("没有指定事项时显示的鼓励文字")
            encouragement.append((slot, edit))
        form.addRow("下班时间", end_time)
        form.addRow("", autostart)
        form.addRow("顶部鼓励语", greeting)
        form.addRow("倒计时待办数量", countdown_count)
        form.addRow("手动固定浮窗位数量", manual_count)
        form.addRow("弹出快捷键", shortcut)
        for slot, edit in encouragement:
            form.addRow(f"浮窗位置 {slot} 鼓励文字", edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        # The two float slot counters are deliberately previewed before saving so
        # the user can see the panel change immediately. Cancel restores saved data.
        countdown_count.valueChanged.connect(
            lambda value: self.refresh_float(countdown_count=value, manual_count=manual_count.value())
        )
        manual_count.valueChanged.connect(
            lambda value: self.refresh_float(countdown_count=countdown_count.value(), manual_count=value)
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.db.set_setting("off_work_time", end_time.time().toString("HH:mm"))
            self.db.set_setting("autostart", "1" if autostart.isChecked() else "0")
            chosen_greeting = greeting.currentText().strip() or greetings[0]
            if chosen_greeting not in greetings and chosen_greeting not in saved_greetings:
                saved_greetings.append(chosen_greeting)
            self.db.set_setting("saved_float_greetings", json.dumps(saved_greetings, ensure_ascii=False))
            self.db.set_setting("float_greeting", chosen_greeting)
            self.db.set_setting("countdown_float_count", str(countdown_count.value()))
            self.db.set_setting("manual_float_count", str(manual_count.value()))
            self.db.set_setting("float_shortcut", shortcut.currentData())
            for slot, edit in encouragement:
                self.db.set_setting(f"float_text_{slot}", edit.text().strip())
            self.set_autostart(autostart.isChecked())
            if shortcut.currentData() != "none" and not self.apply_shortcut(shortcut.currentData()):
                self.show_notice("Alt + E 未能启用，可能正被其他软件占用。")
            self.refresh_float()
        else:
            self.refresh_float()

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
