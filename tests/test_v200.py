"""Focused V3.7 regression checks for settings, reminders, and task views."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QMessageBox

from storage.database import Database
from ui.main_window import MainWindow
from ui.float_window import FloatCard, FloatWindow
from ui.settings_dialog import GuidedTimeCombo, SettingsDialog
from ui.task_dialog import TaskDialog


class FloatAlertSpy:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def show_alert(self, message: str = "") -> None:
        self.messages.append(message)


class TriggerHarness:
    _trigger_float = MainWindow._trigger_float

    def __init__(self, overtime_active: bool = True) -> None:
        self.overtime_active = overtime_active
        self.float_window = FloatAlertSpy()

    def float_is_enabled(self) -> bool:
        return True

    def _overtime_header(self, now: datetime) -> str:
        return "加班1小时了！\n你今天辛苦啦！" if self.overtime_active else ""


class ReminderHarness:
    DEFAULT_GREETINGS = MainWindow.DEFAULT_GREETINGS
    _ensure_v21_greetings = MainWindow._ensure_v21_greetings
    _limit_greeting_lines = staticmethod(MainWindow._limit_greeting_lines)
    _setting_list = MainWindow._setting_list
    _format_hours = staticmethod(MainWindow._format_hours)
    _overtime_reminder_message = MainWindow._overtime_reminder_message
    _check_lifestyle_reminders = MainWindow._check_lifestyle_reminders

    def __init__(self, db: Database) -> None:
        self.db = db

    def _offwork_datetime(self, now: datetime) -> datetime:
        return datetime.strptime(f"{now.date().isoformat()} 18:10", "%Y-%m-%d %H:%M")


class BrandHarness:
    EDITOR_BRAND_GREETINGS = MainWindow.EDITOR_BRAND_GREETINGS
    WEEKEND_BRAND_GREETINGS = MainWindow.WEEKEND_BRAND_GREETINGS
    _editor_brand_message = MainWindow._editor_brand_message

    def __init__(self, db: Database) -> None:
        self.db = db


class MigrationHarness:
    _ensure_v35_float_hint = MainWindow._ensure_v35_float_hint
    _ensure_v37_float_hint_copy = MainWindow._ensure_v37_float_hint_copy

    def __init__(self, db: Database) -> None:
        self.db = db


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
            ["工作与启动", "提醒", "顶部鼓励语", "浮窗显示数量调节", "桌边重点位"],
        )
        reminder_names = [
            checkbox.text()
            for checkbox in dialog.findChildren(QCheckBox)
            if checkbox.text() in {"喝水提醒", "用眼提醒", "吃饭提醒", "下班提醒", "加班提醒"}
        ]
        self.assertEqual(reminder_names, ["喝水提醒", "用眼提醒", "吃饭提醒", "下班提醒", "加班提醒"])
        self.assertEqual(dialog.overtime_cadence.currentData(), "30")

    def test_custom_water_slots_match_time_grid(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        self.assertEqual(len(dialog.water_custom), 3)
        for combo in dialog.water_custom:
            self.assertEqual(combo.currentData(), "")
        self.assertEqual(GuidedTimeCombo.HOURS, tuple(range(7, 23)))
        self.assertEqual(GuidedTimeCombo.MINUTES, (0, 10, 15, 20, 30, 40, 45, 50))
        self.assertTrue(GuidedTimeCombo._valid_value("07:00"))
        self.assertTrue(GuidedTimeCombo._valid_value("22:50"))
        self.assertFalse(GuidedTimeCombo._valid_value("23:00"))
        dialog.water_custom[0].set_value("09:30")
        self.assertTrue(dialog.water_custom[0].property("selected"))
        self.assertEqual(dialog.water_custom[0].text(), "09:30")

    def test_eye_reminder_defaults_and_copy(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        self.assertTrue(dialog.eye_enabled.isChecked())
        self.assertEqual(dialog.values()["eye_fixed_times"], ["11:35", "16:40"])
        self.assertEqual(len(dialog.eye_custom), 3)
        self.db.set_setting("water_enabled", "0")
        self.db.set_setting("meal_enabled", "0")
        self.db.set_setting("offwork_enabled", "0")
        self.db.set_setting("overtime_enabled", "0")
        harness = ReminderHarness(self.db)
        message = harness._check_lifestyle_reminders(datetime(2026, 9, 1, 11, 35, 20))
        self.assertEqual(message, [("eye", "眼睛和你都辛苦啦\n闭上眼 按摩休息一下吧")])

    def test_fixed_water_times_are_individually_selectable(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        self.assertEqual(dialog.values()["water_fixed_times"], ["10:15", "15:15"])
        dialog.water_fixed_buttons[1].setChecked(False)
        self.assertEqual(dialog.values()["water_fixed_times"], ["10:15"])
        self.db.set_setting("water_fixed_times", json.dumps(["10:15"]))
        self.db.set_setting("water_enabled", "1")
        self.db.set_setting("meal_enabled", "0")
        self.db.set_setting("offwork_enabled", "0")
        self.db.set_setting("overtime_enabled", "0")
        harness = ReminderHarness(self.db)
        self.assertEqual(harness._check_lifestyle_reminders(datetime(2026, 9, 1, 15, 15, 20)), [])

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

    def test_v32_corrects_greeting_typo_and_limits_legacy_lines(self) -> None:
        self.db.set_setting(
            "saved_float_greetings",
            json.dumps(["我为亚泰添砖贴瓦", "一\n二\n三\n四"], ensure_ascii=False),
        )
        self.db.set_setting("float_greeting", "我为亚泰添砖贴瓦")
        harness = ReminderHarness(self.db)
        MainWindow._ensure_v32_greetings(harness)
        saved = json.loads(self.db.get_setting("saved_float_greetings"))
        self.assertIn("我为亚泰添砖加瓦", saved)
        self.assertNotIn("我为亚泰添砖贴瓦", saved)
        self.assertIn("一\n二\n三", saved)
        self.assertEqual(self.db.get_setting("float_greeting"), "我为亚泰添砖加瓦")

    def test_brand_copy_is_stable_for_one_clock_hour_then_changes(self) -> None:
        harness = BrandHarness(self.db)
        with patch("ui.main_window.random.choice", side_effect=["让要紧的事，在桌边等你。", "今天也要对自己好一点。"]) as choice:
            first = harness._editor_brand_message(datetime(2026, 9, 1, 10, 5))
            same_hour = harness._editor_brand_message(datetime(2026, 9, 1, 10, 59))
            next_hour = harness._editor_brand_message(datetime(2026, 9, 1, 11, 0))
        self.assertEqual(first, same_hour)
        self.assertNotEqual(first, next_hour)
        self.assertEqual(choice.call_count, 2)

    def test_water_reminder_copy(self) -> None:
        self.db.set_setting("water_enabled", "1")
        self.db.set_setting("meal_enabled", "0")
        self.db.set_setting("offwork_enabled", "0")
        self.db.set_setting("overtime_enabled", "0")
        harness = ReminderHarness(self.db)
        morning = harness._check_lifestyle_reminders(datetime(2026, 9, 1, 10, 15, 20))
        afternoon = harness._check_lifestyle_reminders(datetime(2026, 9, 1, 15, 15, 20))
        self.assertEqual(morning, [("water", "喝水时间到了\n你辛苦啦！")])
        self.assertEqual(afternoon, [("water", "下午三点，饮茶了先！\n你辛苦啦！")])

    def test_overtime_alert_type_does_not_depend_on_copy_spacing(self) -> None:
        harness = TriggerHarness()
        harness._trigger_float("加班5小时了！\n夜深了 回家注意安全哦", reminder_kind="overtime")
        self.assertEqual(harness.float_window.messages, ["加班5小时了！\n夜深了 回家注意安全哦"])
        harness._trigger_float("喝水时间到了\n你辛苦啦！", reminder_kind="water")
        self.assertEqual(harness.float_window.messages[-1], "")

    def test_overtime_copy_uses_half_hour_frequency(self) -> None:
        self.assertEqual(
            MainWindow._overtime_reminder_message(ReminderHarness(self.db), 60),
            "加班1小时了！\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_reminder_message(ReminderHarness(self.db), 90),
            "加班1.5小时了！\n夜深了 回家注意安全哦",
        )

    def test_overtime_display_minute_boundaries(self) -> None:
        harness = ReminderHarness(self.db)
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 18, 10)),
            "正在加班\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 29)),
            "加班1小时了！\n你今天辛苦啦！",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 30)),
            "加班1.5小时了！\n夜深了 回家注意安全哦",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 19, 59)),
            "加班1.5小时了！\n夜深了 回家注意安全哦",
        )
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 1, 20, 0)),
            "加班2小时了！\n夜深了 回家注意安全哦",
        )

    def test_precise_overtime_uses_hours_and_minutes(self) -> None:
        self.assertEqual(MainWindow._format_precise_overtime(30), "已加班 30 分钟")
        self.assertEqual(MainWindow._format_precise_overtime(60), "已加班 1 小时")
        self.assertEqual(MainWindow._format_precise_overtime(123), "已加班 2 小时 3 分钟")

    def test_alert_header_is_exactly_two_lines_without_word_wrap(self) -> None:
        window = FloatWindow()
        message = "加班3小时了！\n夜深了 回家注意安全哦"
        window._apply_header(message, "alert")
        self.assertEqual(window.greeting.text().splitlines(), message.splitlines())
        self.assertFalse(window.greeting.wordWrap())
        self.assertGreaterEqual(window.greeting.height(), 38)

    def test_copied_tasks_are_separate_but_float_deduplicates_them(self) -> None:
        values = {
            "title": "做合同", "notes": "", "task_date": "2026-09-01",
            "due_time": "09:00", "is_fixed": False,
        }
        first_id = self.db.add_task(**values)
        second_id = self.db.add_task(**values)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(self.db.tasks_for("2026-09-01")), 2)
        original = {"id": 1, "title": "做合同", "due_time": "09:00"}
        copied = {"id": 2, "title": "做合同", "due_time": "09:00"}
        unique = MainWindow._deduplicate_countdown_tasks([original, copied], {2})
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["id"], 2)
        dialog = TaskDialog({
            "title": "做合同", "notes": "", "task_date": "2026-09-01",
            "due_time": "09:00", "is_fixed": 0,
        })
        self.assertFalse(dialog.duplicate_check.isHidden())
        dialog.duplicate_check.setChecked(True)
        self.assertTrue(dialog.duplicate_requested())

    def test_past_due_task_is_not_a_new_reminder_schedule(self) -> None:
        past = {"task_date": "2026-09-01", "due_time": "09:00"}
        future = {"task_date": "2026-09-01", "due_time": "18:00"}
        with patch("ui.main_window.datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 1, 15, 0)
            clock.strptime.side_effect = datetime.strptime
            self.assertTrue(MainWindow._is_past_due(past))
            self.assertFalse(MainWindow._is_past_due(future))

    def test_all_tasks_keeps_completed_history(self) -> None:
        first = self.db.add_task("昨天完成", "", "2026-08-31", None, False)
        self.db.set_completed(first, True)
        self.db.add_task("今天未完成", "", "2026-09-01", None, False)
        self.assertEqual([task["title"] for task in self.db.all_tasks()], ["昨天完成", "今天未完成"])

    def test_settings_dirty_state_and_no_wheel_controls(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        initial = dialog._comparison_state()
        dialog.autostart.toggle()
        self.assertNotEqual(dialog._comparison_state(), initial)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel) as shown:
            dialog.reject()
        shown.assert_called_once()

        class FakeWheel:
            ignored = False

            def ignore(self):
                self.ignored = True

        event = FakeWheel()
        dialog.countdown_count.wheelEvent(event)
        self.assertTrue(event.ignored)

    def test_v230_title_is_limited_to_two_lines(self) -> None:
        dialog = TaskDialog()
        dialog.title_edit.setPlainText("第一行\n第二行\n第三行")
        self.assertEqual(dialog.title_edit.document().blockCount(), 2)
        self.assertEqual(dialog.title_edit.toPlainText(), "第一行\n第二行 第三行")

    def test_v320_water_slots_match_meal_chips_and_greeting_shows_two_lines(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        dialog.greeting.setCurrentIndex(1)
        dialog.show()
        self.app.processEvents()
        controls = [*dialog.water_fixed_buttons, *dialog.water_custom]
        self.assertEqual({(control.width(), control.height()) for control in controls}, {(54, 31)})
        self.assertEqual(
            {(control.width(), control.height()) for control in dialog.meal_buttons}, {(54, 31)}
        )
        positions = {control.mapTo(dialog, control.rect().topLeft()).y() for control in controls}
        self.assertEqual(len(positions), 1)
        self.assertEqual(dialog.width(), 560)
        self.assertGreaterEqual(dialog.greeting.height(), 48)
        self.assertIn("\n", dialog.greeting.currentText())

    def test_eye_slots_align_with_water_and_work_controls_share_title_row(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        dialog.show()
        self.app.processEvents()
        water_controls = [*dialog.water_fixed_buttons, *dialog.water_custom]
        eye_controls = [*dialog.eye_fixed_buttons, *dialog.eye_custom]
        self.assertEqual({(item.width(), item.height()) for item in eye_controls}, {(54, 31)})
        water_y = {item.mapTo(dialog, item.rect().topLeft()).y() for item in water_controls}
        eye_y = {item.mapTo(dialog, item.rect().topLeft()).y() for item in eye_controls}
        self.assertEqual(len(water_y), 1)
        self.assertEqual(len(eye_y), 1)
        work_title = next(label for label in dialog.findChildren(QLabel, "sectionTitle") if label.text() == "工作与启动")
        self.assertEqual(work_title.mapTo(dialog, work_title.rect().topLeft()).y(), dialog.end_time.mapTo(dialog, dialog.end_time.rect().topLeft()).y())

    def test_float_hint_migration_keeps_existing_first_phrase_in_place(self) -> None:
        hint = "双击浮窗可打开主页面"
        harness = MigrationHarness(self.db)
        harness._ensure_v35_float_hint()
        self.assertEqual(self.db.get_setting("float_text_1"), hint)

        upgraded = Database(Path(self.temp.name) / "upgrade.db")
        upgraded.set_setting("float_text_1", "保持原有第一条")
        upgraded.set_setting("float_text_2", "")
        MigrationHarness(upgraded)._ensure_v35_float_hint()
        self.assertEqual(upgraded.get_setting("float_text_1"), "保持原有第一条")
        self.assertEqual(upgraded.get_setting("float_text_2"), hint)
        upgraded.set_setting("float_text_2", "双击浮窗内容可打开主页面")
        MigrationHarness(upgraded)._ensure_v37_float_hint_copy()
        self.assertEqual(upgraded.get_setting("float_text_2"), hint)
        upgraded.close()

    def test_float_passive_mode_keeps_hover_controls_available_but_disables_clicks(self) -> None:
        window = FloatWindow()
        window.set_passive_mode(True)
        self.assertFalse(window.hide_button.isEnabled())
        window.set_passive_mode(False)
        self.assertTrue(window.hide_button.isEnabled())

    def test_v320_custom_greeting_stops_at_three_lines(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        dialog.custom_greeting.setPlainText("一\n二\n三\n四")
        self.assertEqual(dialog.custom_greeting.toPlainText(), "一\n二\n三")
        self.assertLessEqual(dialog.custom_greeting.document().blockCount(), 3)
        self.assertEqual(dialog.custom_greeting.minimumHeight(), dialog.custom_greeting.maximumHeight())
        self.assertEqual(dialog.greeting.size(), dialog.custom_greeting.size())

    def test_database_truth_for_priority_slot_is_not_a_stale_card_copy(self) -> None:
        task_id = self.db.add_task("重点事项", "", "2026-09-01", None, False)
        cached_before_assignment = dict(self.db.task_by_id(task_id))
        self.assertIsNone(cached_before_assignment["float_slot"])
        self.db.update_task(task_id, float_slot=2)
        self.assertEqual(self.db.task_by_id(task_id)["float_slot"], 2)
        # The menu now uses this current database row, not the stale copy.
        self.assertIsNone(cached_before_assignment["float_slot"])

    def test_v230_single_line_float_card_is_larger_and_bolder(self) -> None:
        card = FloatCard()
        card.update_card("15:00", "做报价", kind="countdown")
        style = card.text.styleSheet()
        self.assertIn("font-size:15px", style)
        self.assertIn("font-weight:600", style)

    def test_float_placeholder_and_setting_text_have_quieter_visual_weight(self) -> None:
        card = FloatCard()
        card.update_card("1", "", kind="manual", source="empty")
        self.assertEqual(card.text.text(), "暂无固定内容")
        self.assertIn("color:#a8b1bd", card.text.styleSheet())
        self.assertIn("font-weight:400", card.text.styleSheet())
        card.update_card("1", "喝水", kind="manual", source="fixed_text")
        self.assertIn("color:#a8b1bd", card.text.styleSheet())
        self.assertIn("font-weight:400", card.text.styleSheet())

    def test_auto_collapse_choices_and_large_clickable_counter(self) -> None:
        dialog = SettingsDialog(self.db, list(MainWindow.DEFAULT_GREETINGS))
        self.assertEqual(dialog.collapse_delay.currentData(), "4")
        dialog.collapse_delay.setCurrentIndex(dialog.collapse_delay.findData("manual"))
        self.assertEqual(dialog.values()["collapse_delay"], "manual")
        original = dialog.countdown_count.value()
        dialog.countdown_count.plus_button.click()
        self.assertEqual(dialog.countdown_count.value(), original + 1)
        self.assertGreaterEqual(dialog.countdown_count.plus_button.width(), 32)

    def test_completed_task_automatically_leaves_desk_priority_slot(self) -> None:
        task_id = self.db.add_task("今日重点", "", "2026-09-01", None, False)
        self.db.update_task(task_id, float_slot=1)
        self.assertEqual(self.db.float_tasks()[0]["float_slot"], 1)
        self.db.set_completed(task_id, True)
        task = self.db.tasks_for("2026-09-01")[0]
        self.assertEqual(task["float_slot"], None)
        self.assertEqual(self.db.float_tasks(), [])

    def test_untimed_tasks_fill_the_bottom_of_countdown_slots(self) -> None:
        def task(task_id, title, due_time=None):
            return {"id": task_id, "title": title, "due_time": due_time}

        cards = MainWindow._countdown_cards([], [task(1, "整理资料")], 3)
        self.assertEqual([card[1] for card in cards], ["", "", "整理资料"])
        cards = MainWindow._countdown_cards([], [task(1, "整理资料"), task(2, "联系客户")], 4)
        self.assertEqual([card[1] for card in cards], ["", "", "整理资料", "联系客户"])
        cards = MainWindow._countdown_cards(
            [task(3, "15点会议", "15:00")], [task(1, "整理资料")], 3
        )
        self.assertEqual([card[1] for card in cards], ["15点会议", "", "整理资料"])


if __name__ == "__main__":
    unittest.main()
