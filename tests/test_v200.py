"""Focused V2.1.0 regression checks for settings and reminder rules."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel

from storage.database import Database
from ui.main_window import MainWindow
from ui.settings_dialog import GuidedTimeCombo, SettingsDialog


class ReminderHarness:
    DEFAULT_GREETINGS = MainWindow.DEFAULT_GREETINGS
    _ensure_v21_greetings = MainWindow._ensure_v21_greetings
    _setting_list = MainWindow._setting_list
    _format_hours = staticmethod(MainWindow._format_hours)
    _overtime_reminder_message = MainWindow._overtime_reminder_message
    _check_lifestyle_reminders = MainWindow._check_lifestyle_reminders

    def __init__(self, db: Database) -> None:
        self.db = db

    def _offwork_datetime(self, now: datetime) -> datetime:
        return datetime.strptime(f"{now.date().isoformat()} 18:10", "%Y-%m-%d %H:%M")


class V200Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "work-todo.db")

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_settings_sections_and_reminder_order(self) -> None:
        self.assertEqual(
            MainWindow.DEFAULT_GREETINGS,
            ["我为亚泰添砖加瓦", "工作辛苦\n你也要保持开心鸭！", "慢慢推进\n今天非常棒！"],
        )
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        titles = [label.text() for label in dialog.findChildren(QLabel, "sectionTitle")]
        self.assertEqual(
            titles,
            ["工作与启动", "提醒", "顶部鼓励语", "浮窗显示数量调节", "浮窗固定文字"],
        )
        reminder_names = [
            checkbox.text()
            for checkbox in dialog.findChildren(QCheckBox)
            if checkbox.text() in {"喝水提醒", "吃饭提醒", "下班提醒", "加班提醒"}
        ]
        self.assertEqual(reminder_names, ["喝水提醒", "吃饭提醒", "下班提醒", "加班提醒"])

    def test_custom_water_slots_match_time_grid(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        self.assertEqual(len(dialog.water_custom), 3)
        for combo in dialog.water_custom:
            self.assertEqual(combo.currentData(), "")
        self.assertEqual(GuidedTimeCombo.HOURS, tuple(range(7, 23)))
        self.assertEqual(GuidedTimeCombo.MINUTES, (0, 10, 20, 30, 40, 50))
        self.assertTrue(GuidedTimeCombo._valid_value("07:00"))
        self.assertTrue(GuidedTimeCombo._valid_value("22:50"))
        self.assertFalse(GuidedTimeCombo._valid_value("23:00"))

    def test_greeting_editor_preserves_manual_line_breaks(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        text = "工作辛苦\n你也要保持开心鸭！"
        dialog.custom_greeting.setPlainText(text)
        dialog._save_custom_greeting()
        self.assertEqual(dialog.greeting.currentText(), text)
        self.assertIn(text, dialog.values()["greetings"])

    def test_v21_removes_retired_default_greeting(self) -> None:
        retired = "稳稳完成眼前这一件就好。"
        self.db.set_setting(
            "saved_float_greetings",
            json.dumps([retired, "我的自定义文字"], ensure_ascii=False),
        )
        self.db.set_setting("float_greeting", retired)
        harness = ReminderHarness(self.db)
        harness._ensure_v21_greetings()
        saved = json.loads(self.db.get_setting("saved_float_greetings"))
        self.assertNotIn(retired, saved)
        self.assertIn("我的自定义文字", saved)
        self.assertEqual(self.db.get_setting("float_greeting"), "我为亚泰添砖加瓦")

    def test_water_reminder_copy(self) -> None:
        self.db.set_setting("water_enabled", "1")
        self.db.set_setting("meal_enabled", "0")
        self.db.set_setting("offwork_enabled", "0")
        self.db.set_setting("overtime_enabled", "0")
        harness = ReminderHarness(self.db)
        morning = harness._check_lifestyle_reminders(datetime(2026, 9, 1, 10, 15, 20))
        afternoon = harness._check_lifestyle_reminders(datetime(2026, 9, 1, 15, 15, 20))
        self.assertEqual(morning, ["喝水时间到了\n你辛苦啦！"])
        self.assertEqual(afternoon, ["下午三点，饮茶了先！\n你辛苦啦！"])

    def test_overtime_copy_uses_half_hour_frequency(self) -> None:
        self.assertEqual(
            MainWindow._overtime_reminder_message(ReminderHarness(self.db), 60),
            "加班 1 小时了\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_reminder_message(ReminderHarness(self.db), 90),
            "加班 1.5 小时了\n夜深了 回家注意安全哦",
        )

    def test_overtime_display_minute_boundaries(self) -> None:
        harness = ReminderHarness(self.db)
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 18, 10)),
            "正在加班\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 29)),
            "加班 1 小时了\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 30)),
            "加班 1.5 小时了\n夜深了 回家注意安全哦",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 59)),
            "加班 1.5 小时了\n夜深了 回家注意安全哦",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 20, 0)),
            "加班 2 小时了\n夜深了 回家注意安全哦",
        )


if __name__ == "__main__":
    unittest.main()
