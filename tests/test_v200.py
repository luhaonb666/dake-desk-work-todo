"""Focused V4.7.0 regression checks for settings, reminders, and task views."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QDate, QEvent, QMimeData, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QMessageBox

from storage.database import Database
from services.windows_notifications import planned_reminders
from ui.main_window import ExpandableNotesWidget, ExpandableStepsPreview, FadedPreviewLine, MainWindow
from ui.float_window import FloatCard, FloatWindow
from ui.controls import CompactDatePicker, normalize_note_text
from ui.desktop_note import DesktopNoteDialog, DesktopNoteWindow
from ui.important_reminder import ImportantReminderWindow
from ui.settings_dialog import GuidedTimeCombo, SettingsDialog
from ui.task_dialog import PlainNotesEditor, TaskDialog
from ui.task_steps import TaskStepsEditor
from ui.workspace_editor import WorkspaceEditor


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

    def test_lifestyle_alert_keeps_its_own_copy_during_overtime(self) -> None:
        harness = TriggerHarness()
        harness._trigger_float("加班5小时了！\n夜深了 回家注意安全哦", reminder_kind="overtime")
        self.assertEqual(harness.float_window.messages, ["加班5小时了！\n夜深了 回家注意安全哦"])
        harness._trigger_float("喝水时间到了\n你辛苦啦！", reminder_kind="water")
        self.assertEqual(harness.float_window.messages[-1], "喝水时间到了\n你辛苦啦！")

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
        self.assertEqual(
            MainWindow._overtime_header(harness, datetime(2026, 9, 2, 0, 0)),
            "",
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
        self.assertFalse(dialog.follow_up_button.isHidden())
        self.assertEqual(dialog.follow_up_button.text(), "保留原事项，另建后续")
        self.assertFalse(dialog.duplicate_requested())

    def test_workspace_editor_waits_for_explicit_save(self) -> None:
        task_id = self.db.add_task("原事项", "第一行\n第二行", "2026-09-01", "09:00", False)
        editor = WorkspaceEditor()
        editor.load_task(self.db.task_by_id(task_id))
        editor.title_edit.setPlainText("修改后事项")
        self.assertTrue(editor.is_dirty())
        # Editing the right-hand workspace form never writes to SQLite by itself.
        self.assertEqual(self.db.task_by_id(task_id)["title"], "原事项")
        saved: list[tuple[int, dict]] = []
        editor.save_requested.connect(lambda saved_id, values: saved.append((saved_id, values)))
        editor._emit_save()
        self.assertEqual(saved[0][0], task_id)
        self.assertEqual(saved[0][1]["title"], "修改后事项")
        self.assertEqual(saved[0][1]["notes"], "第一行\n第二行")

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

    def test_fixed_tasks_has_its_own_workspace_category_source(self) -> None:
        self.db.add_task("普通事项", "", "2026-09-01", None, False)
        fixed = self.db.add_task("固定事项", "", "2026-09-02", "10:00", True)
        self.db.set_completed(fixed, True)
        self.assertEqual([task["title"] for task in self.db.fixed_tasks()], ["固定事项"])

    def test_windows_reminder_choice_stays_visible_until_time_is_selected(self) -> None:
        dialog = TaskDialog()
        self.assertFalse(dialog.important_reminder_check.isHidden())
        self.assertTrue(dialog.important_reminder_check.isEnabled())
        dialog.time_enabled.setChecked(True)
        self.assertTrue(dialog.important_reminder_check.isEnabled())

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
        self.assertEqual(
            dialog.greeting.mapTo(dialog, dialog.greeting.rect().topLeft()).x(),
            dialog.custom_greeting.mapTo(dialog, dialog.custom_greeting.rect().topLeft()).x(),
        )

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
        self.assertIn("font-size:16px", style)
        self.assertIn("font-weight:600", style)

    def test_float_placeholder_and_setting_text_have_quieter_visual_weight(self) -> None:
        card = FloatCard()
        card.update_card("1", "", kind="manual", source="empty")
        self.assertEqual(card.text.text(), "暂无固定内容")
        self.assertIn("color:#bac2cc", card.text.styleSheet())
        self.assertIn("font-weight:400", card.text.styleSheet())
        self.assertIn("font-size:11px", card.text.styleSheet())
        card.update_card("1", "喝水", kind="manual", source="fixed_text")
        self.assertIn("color:#768393", card.text.styleSheet())
        self.assertIn("font-weight:550", card.text.styleSheet())

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

    def test_task_editor_keeps_saved_note_line_breaks(self) -> None:
        task = {
            "title": "核对方案",
            "notes": "第一行\n第二行\n第三行",
            "task_date": "2026-09-01",
            "due_time": None,
            "is_fixed": False,
        }
        dialog = TaskDialog(task)
        self.assertEqual(dialog.notes_edit.toPlainText(), task["notes"])
        self.assertEqual(dialog.values()["notes"], task["notes"])

    def test_important_reminder_has_independent_schedule_modes(self) -> None:
        dialog = TaskDialog()
        self.assertFalse(dialog.important_reminder_check.isHidden())
        self.assertTrue(dialog.important_reminder_check.isEnabled())
        self.assertTrue(dialog.event_type_box.isHidden())
        self.assertTrue(dialog.recurrence_box.isHidden())
        self.assertFalse(dialog.important_reminder_check.isChecked())
        dialog.time_enabled.setChecked(True)
        dialog.important_schedule._set_mode("follow")
        dialog.important_reminder_check.setChecked(True)
        dialog.important_schedule._set_offset(30)
        self.assertTrue(dialog.values()["windows_reminder_enabled"])
        self.assertEqual(dialog.values()["important_reminder_offset_minutes"], 30)
        self.assertIsNone(dialog.values()["important_reminder_at"])
        dialog.important_schedule.custom_offset.setCurrentIndex(
            dialog.important_schedule.custom_offset.findData(180)
        )
        self.assertEqual(dialog.values()["important_reminder_offset_minutes"], 180)
        dialog.important_schedule._set_mode("deadline")
        self.assertEqual(dialog.values()["important_reminder_mode"], "deadline")
        self.assertTrue(dialog.values()["windows_reminder_enabled"])
        self.assertFalse(dialog.add_step_button.isHidden())

    def test_v467_important_reminder_opens_from_a_focused_editor_entry(self) -> None:
        dialog = TaskDialog()
        self.assertEqual(dialog.open_important_editor_button.text(), "重要提醒设置")
        self.assertTrue(dialog.important_schedule.isHidden())
        dialog.important_reminder_check.setChecked(True)
        self.assertEqual(dialog.open_important_editor_button.text(), "重要提醒设置")
        self.assertTrue(dialog.important_schedule.isHidden())
        self.assertTrue(dialog.follow_up_button.isHidden())

    def test_v468_quick_important_reminder_keeps_simple_offsets_in_the_main_editor(self) -> None:
        dialog = TaskDialog()
        dialog._set_quick_reminder_offset(30)
        values = dialog.values()
        self.assertTrue(values["windows_reminder_enabled"])
        self.assertEqual(values["important_reminder_mode"], "follow")
        self.assertEqual(values["important_reminder_offset_minutes"], 30)
        self.assertTrue(dialog.time_enabled.isChecked())
        self.assertTrue(dialog.quick_reminder_buttons[30].isChecked())
        self.assertIn("需手动关闭", dialog.reminder_summary.text())

    def test_v467_deadline_target_is_independent_from_the_task_date(self) -> None:
        task_id = self.db.add_task(
            "月底提交材料", "", "2026-09-16", None, False,
            windows_reminder_enabled=True,
            important_reminder_mode="deadline",
            important_reminder_target_date="2026-09-30",
            important_reminder_time="12:00",
            important_reminder_lead_days=7,
        )
        task = self.db.task_by_id(task_id)
        self.assertEqual(task["task_date"], "2026-09-16")
        self.assertEqual(task["important_reminder_target_date"], "2026-09-30")
        self.assertEqual(
            [item["id"] for item in self.db.pending_important_reminder_tasks(datetime(2026, 9, 23, 12, 0))],
            [task_id],
        )

    def test_reminder_event_hides_but_preserves_existing_steps(self) -> None:
        task_id = self.db.add_task("会议准备", "带齐材料", "2026-09-01", "10:00", False)
        self.db.replace_task_steps(task_id, [{"content": "打印资料", "is_completed": False}])
        dialog = TaskDialog(self.db.task_by_id(task_id), task_steps=self.db.task_steps(task_id))
        dialog._set_event_type("reminder")
        values = dialog.values()
        self.assertEqual(values["event_type"], "reminder")
        self.assertEqual(values["steps"], [{"content": "打印资料", "is_completed": False}])
        self.db.update_task(task_id, event_type=values["event_type"])
        self.assertEqual(self.db.task_by_id(task_id)["event_type"], "reminder")
        self.assertEqual(self.db.task_steps(task_id)[0]["content"], "打印资料")

    def test_v466_deadline_plan_starts_early_and_keeps_reminding_after_target(self) -> None:
        task_id = self.db.add_task(
            "9 月底提交材料", "", "2026-09-30", None, False,
            windows_reminder_enabled=True,
            important_reminder_mode="deadline",
            important_reminder_time="12:00",
            important_reminder_lead_days=7,
        )
        self.assertEqual(
            self.db.pending_important_reminder_tasks(datetime(2026, 9, 22, 12, 0)), []
        )
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 23, 12, 0))],
            [task_id],
        )
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 10, 1, 12, 0))],
            [task_id],
        )
        self.db.cancel_important_reminder(task_id)
        self.assertEqual(self.db.pending_important_reminder_tasks(datetime(2026, 10, 2, 12, 0)), [])

    def test_v466_weekly_plan_does_not_change_the_task_date_or_time(self) -> None:
        task_id = self.db.add_task(
            "交给领导的表格", "", "2026-09-16", None, False,
            windows_reminder_enabled=True,
            important_reminder_mode="weekly",
            important_reminder_start_date="2026-09-16",
            important_reminder_time="12:00",
            important_reminder_weekday=3,
        )
        task = self.db.task_by_id(task_id)
        self.assertEqual(task["task_date"], "2026-09-16")
        self.assertIsNone(task["due_time"])
        self.assertEqual(
            [item["id"] for item in self.db.pending_important_reminder_tasks(datetime(2026, 9, 16, 12, 0))],
            [task_id],
        )
        self.assertEqual(self.db.pending_important_reminder_tasks(datetime(2026, 9, 17, 12, 0)), [])

    def test_v470_periodic_reminder_supports_day_and_week_intervals(self) -> None:
        every_three_days = self.db.add_task(
            "每三天检查", "", "2026-09-16", None, False,
            windows_reminder_enabled=True,
            important_reminder_mode="weekly",
            important_reminder_start_date="2026-09-16",
            important_reminder_time="12:00",
            important_reminder_repeat_unit="day",
            important_reminder_repeat_interval=3,
        )
        every_two_weeks = self.db.add_task(
            "双周例会", "", "2026-09-16", None, False,
            windows_reminder_enabled=True,
            important_reminder_mode="weekly",
            important_reminder_start_date="2026-09-16",
            important_reminder_time="12:00",
            important_reminder_weekday=3,
            important_reminder_repeat_unit="week",
            important_reminder_repeat_interval=2,
        )
        self.assertEqual(
            {task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 19, 12, 0))},
            {every_three_days},
        )
        self.assertEqual(
            {task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 30, 12, 0))},
            {every_two_weeks},
        )

    def test_v470_periodic_editor_keeps_repeat_controls_in_its_existing_mode(self) -> None:
        dialog = TaskDialog()
        dialog.important_schedule._set_mode("weekly")
        schedule = dialog.important_schedule
        schedule.repeat_frequency.setCurrentIndex(schedule._repeat_preset_index("custom", 0))
        schedule.repeat_unit.setCurrentIndex(schedule.repeat_unit.findData("day"))
        schedule.repeat_interval.setValue(3)
        values = schedule.values()
        self.assertEqual(values["important_reminder_repeat_unit"], "day")
        self.assertEqual(values["important_reminder_repeat_interval"], 3)
        self.assertFalse(schedule.custom_repeat_row.isHidden())

    def test_v470_past_date_without_time_is_past_due(self) -> None:
        self.assertTrue(MainWindow._is_past_due({"task_date": "2020-01-01", "due_time": None}))

    def test_system_reminder_plan_excludes_past_and_non_opted_in_items(self) -> None:
        enabled = self.db.add_task("重要会议", "", "2026-09-01", "10:00", False, True)
        self.db.add_task("普通事项", "", "2026-09-01", "11:00", False, False)
        self.db.add_task("已经过去", "", "2026-09-01", "09:00", False, True)
        plan = planned_reminders(
            self.db.future_windows_reminder_tasks(datetime(2026, 9, 1, 9, 30)),
            datetime(2026, 9, 1, 9, 30),
        )
        self.assertEqual([(item.task_id, item.title, item.due_time) for item in plan], [(enabled, "重要会议", "10:00")])

    def test_important_reminder_can_trigger_before_the_task_time(self) -> None:
        task_id = self.db.add_task(
            "合同提醒", "", "2026-09-01", "10:00", False, True,
            important_reminder_offset_minutes=30,
        )
        pending = self.db.pending_important_reminder_tasks(datetime(2026, 9, 1, 9, 30))
        self.assertEqual([task["id"] for task in pending], [task_id])

    def test_early_important_reminder_explains_that_it_is_early(self) -> None:
        task_id = self.db.add_task(
            "合同提醒", "", "2026-09-01", "10:00", False, True,
            important_reminder_offset_minutes=30,
        )
        reminder = ImportantReminderWindow()
        reminder.sync_tasks([self.db.task_by_id(task_id)])
        self.assertIn("提前 30 分钟", reminder.time_label.text())
        reminder.hide()

    def test_important_reminder_waits_for_manual_acknowledgement(self) -> None:
        important = self.db.add_task("签合同", "等对方确认", "2026-09-01", "10:00", False, True)
        now = datetime(2026, 9, 1, 10, 1)
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(now)], [important]
        )
        self.db.acknowledge_important_reminder(important)
        self.assertEqual(self.db.pending_important_reminder_tasks(now), [])
        self.db.update_task(important, task_date="2026-09-01", due_time="10:10")
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 1, 10, 11))],
            [important],
        )

    def test_important_reminder_can_snooze_without_completing_task(self) -> None:
        important = self.db.add_task("签合同", "等对方确认", "2026-09-01", "10:00", False, True)
        now = datetime(2026, 9, 1, 10, 1)
        self.db.snooze_important_reminder(important, 10, now)
        self.assertEqual(self.db.pending_important_reminder_tasks(datetime(2026, 9, 1, 10, 10)), [])
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 1, 10, 11))],
            [important],
        )
        self.assertEqual(self.db.task_by_id(important)["is_completed"], 0)

    def test_custom_important_reminder_and_recurrence_are_independent(self) -> None:
        important = self.db.add_task(
            "周报", "整理本周工作", "2026-09-01", "10:00", False, True,
            important_reminder_at="2026-09-01 09:15", recurrence_unit="week",
        )
        self.assertEqual(
            [task["id"] for task in self.db.pending_important_reminder_tasks(datetime(2026, 9, 1, 9, 15))],
            [important],
        )
        self.db.set_completed(important, True)
        next_id = self.db.create_next_recurrence(important)
        self.assertIsNotNone(next_id)
        follow_up = self.db.task_by_id(next_id)
        expected_date = Database.next_recurrence_date("2026-09-01", "week", 1)
        self.assertEqual(follow_up["task_date"], expected_date)
        self.assertEqual(follow_up["important_reminder_at"], f"{expected_date} 09:15")

    def test_task_steps_are_optional_and_keep_parent_completion_separate(self) -> None:
        task_id = self.db.add_task("完成报价", "", "2026-09-01", None, False)
        self.db.replace_task_steps(task_id, [
            {"content": "核价", "is_completed": True},
            {"content": "盖章", "is_completed": True},
        ])
        self.assertEqual(self.db.step_summaries([task_id]), {task_id: (2, 2)})
        self.assertEqual(self.db.task_by_id(task_id)["is_completed"], 0)
        editor = TaskStepsEditor()
        editor.set_steps(self.db.task_steps(task_id))
        self.assertIn("自行勾选整条事项", editor.guide.text())

    def test_v452_step_button_creates_the_first_multiline_step_immediately(self) -> None:
        editor = TaskStepsEditor()
        editor.start_button.click()
        self.assertEqual(len(editor._rows()), 1)
        self.assertEqual(editor._rows()[0].edit.toPlainText(), "")
        editor._rows()[0].edit.setPlainText("核价\n确认折扣")
        self.assertEqual(editor.values()[0]["content"], "核价\n确认折扣")

    def test_v457_step_editor_browses_at_real_height_then_uses_stable_edit_height(self) -> None:
        editor = TaskStepsEditor()
        editor.start()
        row = editor._rows()[0]
        one_line_height = row.height()
        row._set_editing(True)
        editing_height = row.height()
        self.assertGreater(editing_height, one_line_height)
        row.edit.setPlainText("一\n二\n三")
        self.assertEqual(row.height(), editing_height)
        row.edit.setPlainText("一\n二\n三\n四\n五")
        capped_height = row.height()
        row.edit.setPlainText("一\n二\n三\n四\n五\n六\n七")
        self.assertEqual(row.height(), capped_height)
        row._set_editing(False)
        QApplication.instance().processEvents()
        self.assertEqual(row.height(), capped_height)
        row.edit.setPlainText("只有一行")
        self.assertEqual(row.height(), editing_height)
        reloaded = TaskStepsEditor()
        reloaded.set_steps([{"content": "只有一行", "is_completed": False}])
        self.assertEqual(reloaded._rows()[0].height(), one_line_height)

    def test_v457_step_enter_advances_and_split_remains_available(self) -> None:
        editor = TaskStepsEditor()
        editor.add_row("核价", focus=False)
        editor.add_row("盖章", focus=False)
        advanced = []
        editor.next_field_requested.connect(lambda: advanced.append(True))
        first = editor._rows()[0]
        first.edit.keyPressEvent(QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        ))
        self.assertTrue(editor._rows()[1]._editing)
        self.assertNotIn("\n", first.edit.toPlainText())
        editor.confirm_row(editor._rows()[1])
        self.assertEqual(advanced, [True])

        dialog = TaskDialog()
        dialog.notes_edit.setPlainText("核价\n盖章")
        dialog.import_steps_button.click()
        self.assertTrue(dialog.import_steps_button.isEnabled())
        self.assertIn("拆成步骤", dialog.import_steps_button.text())
        self.assertEqual(dialog.import_steps_rail.height(), dialog.notes_edit.height())

    def test_v458_previous_item_explains_two_distinct_continuation_actions(self) -> None:
        task_id = self.db.add_task("旧项目", "", "2026-09-01", None, False)
        editor = WorkspaceEditor()
        editor.load_task(self.db.task_by_id(task_id))
        self.assertEqual(editor.operations_label.text(), "继续处理方式")
        self.assertEqual(editor.move_today_button.text(), "安排到今天继续处理")
        self.assertIn("不会新建副本", editor.move_today_hint.text())
        self.assertEqual(editor.duplicate_button.text(), "保留原事项，另建后续")
        self.assertIn("原事项会保留", editor.duplicate_hint.text())

    def test_v465_current_item_keeps_the_follow_up_explanation(self) -> None:
        task_id = self.db.add_task("当前项目", "", self.db.today(), None, False)
        editor = WorkspaceEditor()
        editor.load_task(self.db.task_by_id(task_id))
        self.assertFalse(editor.duplicate_hint.isHidden())
        self.assertIn("分项进度重新开始", editor.duplicate_hint.text())
        self.assertTrue(editor.move_today_button.isHidden())

    def test_v453_step_plus_inserts_directly_below_the_current_step(self) -> None:
        editor = TaskStepsEditor()
        editor.start_button.click()
        editor._rows()[0].edit.setPlainText("核价")
        editor._rows()[0].insert.click()
        editor._rows()[1].edit.setPlainText("盖章")
        editor._rows()[0].insert.click()
        self.assertEqual(len(editor._rows()), 3)
        self.assertEqual([row.edit.toPlainText() for row in editor._rows()], ["核价", "", "盖章"])
        self.assertNotIn("新建步骤", editor.panel.findChild(QLabel).text())

    def test_v453_step_preview_has_indented_rows_and_can_expand(self) -> None:
        preview = ExpandableStepsPreview([
            {"content": "核价\n确认折扣", "is_completed": False},
            {"content": "盖章", "is_completed": False},
            {"content": "付款", "is_completed": True},
            {"content": "提交报告", "is_completed": False},
        ])
        self.assertEqual(preview.heading.text(), "待办步骤  1/4")
        self.assertEqual(preview._summary(preview._steps[0]), "· 核价、确认折扣")
        self.assertFalse(preview.rows_layout.itemAt(0).widget().wordWrap())
        self.assertEqual(preview.hint.text(), "↓ 点击展开全部待办步骤")
        preview._collapsed = False
        preview._update_text()
        self.assertEqual(preview.rows_layout.count(), 4)
        self.assertEqual(preview.hint.text(), "↑ 点击收起待办步骤")

    def test_v453_import_steps_is_a_framed_explained_action(self) -> None:
        dialog = TaskDialog()
        self.assertIsNotNone(dialog.notes_section)
        self.assertEqual(dialog.import_steps_hint.text(), "按每行\n新增一步\n\n正文保留")
        self.assertIn("原正文不会删除", dialog.import_steps_hint.toolTip())
        self.assertIn("拆成步骤", dialog.import_steps_button.text())
        self.assertEqual(dialog.import_steps_rail.width(), 72)

    def test_v469_workspace_body_is_the_only_flexible_editor_area(self) -> None:
        editor = WorkspaceEditor()
        self.assertEqual(editor.title_edit.height(), 56)
        self.assertGreaterEqual(editor.notes_edit.minimumHeight(), 170)
        editor.steps_editor.start()
        self.assertGreaterEqual(editor.notes_edit.minimumHeight(), 170)
        editor.steps_editor.add_row(focus=False)
        self.assertGreaterEqual(editor.notes_edit.minimumHeight(), 170)
        editor.steps_editor.remove_row(editor.steps_editor._rows()[1])
        self.assertGreaterEqual(editor.notes_edit.minimumHeight(), 170)

    def test_v469_complex_reminder_disables_simple_reminder_choices(self) -> None:
        dialog = TaskDialog()
        dialog.important_reminder_check.setChecked(True)
        dialog.important_schedule._set_mode("deadline")
        dialog._refresh_quick_reminder_controls()
        self.assertFalse(dialog.quick_reminder_buttons[0].isEnabled())
        self.assertFalse(dialog.quick_reminder_custom.isEnabled())
        self.assertIn("简单提醒不可叠加", dialog.quick_reminder_notice.text())
        self.assertEqual(dialog.important_schedule.mode_buttons["deadline"].text(), "目标日提醒")
        self.assertGreaterEqual(dialog.open_important_editor_button.minimumWidth(), 190)

    def test_v469_note_management_no_longer_offers_summary_folding(self) -> None:
        note = DesktopNoteDialog({"text": "第一行\n" * 9, "color": "warm_yellow", "fold_long_content": True}, True)
        self.assertFalse(hasattr(note, "fold"))
        self.assertFalse(note.values()["fold_long_content"])

    def test_v453_desktop_note_is_not_a_global_topmost_window(self) -> None:
        note = DesktopNoteWindow()
        self.assertFalse(bool(note.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        note.enter_editing()
        self.assertFalse(note.close_note_button.isHidden())
        note.deleteLater()

    def test_v452_steps_and_notes_are_parallel_and_notes_import_as_steps(self) -> None:
        dialog = TaskDialog()
        dialog.notes_edit.setPlainText("核价\n盖章\n发送")
        dialog.steps_editor.start_button.click()
        self.assertFalse(dialog.notes_edit.isHidden())
        self.assertFalse(dialog.steps_editor.panel.isHidden())
        self.assertEqual(len(dialog.steps_editor._rows()), 1)
        dialog.import_steps_button.click()
        self.assertEqual(
            [step["content"] for step in dialog.values()["steps"]], ["核价", "盖章", "发送"]
        )
        self.assertEqual(dialog.values()["notes"], "核价\n盖章\n发送")

    def test_v452_desktop_note_construction_handles_early_qt_events(self) -> None:
        note = DesktopNoteWindow()
        self.assertIsNotNone(note.resize_hint)
        self.assertIsNotNone(note.drag_handle)
        note.deleteLater()

    def test_v452_workspace_editor_creates_the_note_target_before_connecting(self) -> None:
        editor = WorkspaceEditor()
        self.assertIsNotNone(editor.notes_edit)
        self.assertIsNotNone(editor.title_edit)
        editor.deleteLater()

    def test_v452_content_mode_preserves_compatibility_for_existing_tasks(self) -> None:
        task_id = self.db.add_task(
            "完成报价", "", "2026-09-01", None, False, content_mode="steps"
        )
        self.assertEqual(self.db.task_by_id(task_id)["content_mode"], "steps")
        self.db.update_task(task_id, content_mode="notes")
        self.assertEqual(self.db.task_by_id(task_id)["content_mode"], "notes")

    def test_unchanged_time_does_not_rearm_a_reminder(self) -> None:
        task_id = self.db.add_task("重要会议", "初稿", "2026-09-01", "10:00", False)
        self.db.mark_alerted(task_id, "pre")
        self.db.mark_alerted(task_id, "due")
        self.db.update_task(task_id, notes="补充说明", task_date="2026-09-01", due_time="10:00")
        task = self.db.task_by_id(task_id)
        self.assertIsNotNone(task["pre_alerted_at"])
        self.assertIsNotNone(task["due_alerted_at"])

    def test_plain_notes_paste_ignores_rich_text_and_keeps_one_real_break(self) -> None:
        source = QMimeData()
        source.setHtml("<p>第一行</p><p>第二行</p>")
        source.setText("第一行\r\n第二行")
        editor = PlainNotesEditor()
        editor.insertFromMimeData(source)
        self.assertEqual(editor.toPlainText(), "第一行\n第二行")
        self.assertEqual(normalize_note_text("一\r二\u2028三\u2029四"), "一\n二\n三\n四")

    def test_note_summary_shows_three_lines_with_a_clear_expand_affordance(self) -> None:
        notes = "第一行\n第二行\n第三行\n第四行"
        widget = ExpandableNotesWidget(notes)
        self.assertEqual(widget.summary.text(), "第一行\n第二行\n第三行")
        self.assertFalse(widget.peek.isHidden())
        self.assertEqual(widget.peek._text, "第四行")
        self.assertEqual(widget.hint.text(), "↓ 点击展开完整说明")
        self.assertTrue(widget.cursor().shape().name.endswith("PointingHandCursor"))
        widget._collapsed = False
        widget._update_text()
        self.assertEqual(widget.summary.text(), notes)
        self.assertTrue(widget.peek.isHidden())
        self.assertEqual(widget.hint.text(), "↑ 点击收起说明")

    def test_faded_note_preview_uses_native_rounded_container(self) -> None:
        # Keep the fourth-line effect out of PyQt's platform-sensitive custom
        # painter overloads entirely.
        preview = FadedPreviewLine("第四行")
        self.assertEqual(preview.line.text(), "第四行")
        self.assertEqual(preview.height(), 11)

    def test_compact_date_picker_supports_shared_date_selection(self) -> None:
        picker = CompactDatePicker(QDate(2026, 9, 4))
        picker.setDate(QDate(2026, 9, 6))
        self.assertEqual(picker.date(), QDate(2026, 9, 6))
        self.assertIn("9 月 6 日", picker.button.text())

    def test_collapsed_float_keeps_time_badge_in_its_visible_left_edge(self) -> None:
        window = FloatWindow()
        card = FloatCard()
        self.assertEqual(window.PEEK_WIDTH, 31)
        self.assertLessEqual(card.layout().contentsMargins().left() + card.badge.width() + 7, window.PEEK_WIDTH)


if __name__ == "__main__":
    unittest.main()
