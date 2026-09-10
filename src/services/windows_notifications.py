"""Opt-in native Windows reminder notifications.

The main app remains local and offline.  This module only registers/schedules
notifications for tasks the user has explicitly marked as important.  Imports
are intentionally deferred: macOS development and an unavailable Windows
notification service must never stop the to-do app from opening.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Protocol


APP_NAME = "大可桌边"
APP_AUMID = "DaKe.DaKeDesk"


@dataclass(frozen=True)
class ScheduledReminder:
    task_id: int
    when: datetime
    title: str
    due_time: str


def planned_reminders(tasks: Iterable, now: datetime) -> list[ScheduledReminder]:
    """Build an OS-neutral plan; easy to test without a Windows computer."""
    reminders: list[ScheduledReminder] = []
    for task in tasks:
        try:
            when = datetime.strptime(f"{task['task_date']} {task['due_time']}", "%Y-%m-%d %H:%M")
        except (KeyError, TypeError, ValueError):
            continue
        if when > now:
            reminders.append(
                ScheduledReminder(
                    task_id=int(task["id"]),
                    when=when,
                    title=str(task["title"]),
                    due_time=str(task["due_time"]),
                )
            )
    return reminders


class _Toaster(Protocol):
    def clear_scheduled_toasts(self) -> None: ...

    def schedule_toast(self, toast, display_time: datetime) -> None: ...


class WindowsReminderService:
    """Small boundary around WinRT's reminder notifications.

    Windows owns the final display decision: Focus Assist, Do Not Disturb, and
    a user disabling app notifications cannot be overridden by an application.
    """

    def __init__(self) -> None:
        self._toaster: _Toaster | None = None
        self._toast_type = None
        self._scenario = None
        self._dismiss_button_type = None
        self._dismiss_action = None
        self.error: str = ""
        self._load_backend()

    @property
    def available(self) -> bool:
        return self._toaster is not None

    def _load_backend(self) -> None:
        if sys.platform != "win32":
            self.error = "当前不是 Windows 系统。"
            return
        try:
            # The package wraps Windows 10/11 WinRT toast APIs.  The installer
            # assigns the same AUMID to the Start-menu shortcut.
            from windows_toasts import (
                InteractableWindowsToaster,
                Toast,
                ToastScenario,
                ToastSystemButton,
                ToastSystemButtonAction,
            )

            self._toaster = InteractableWindowsToaster(APP_NAME, notifierAUMID=APP_AUMID)
            self._toast_type = Toast
            self._scenario = ToastScenario.Reminder
            self._dismiss_button_type = ToastSystemButton
            self._dismiss_action = ToastSystemButtonAction.Dismiss
        except Exception as exc:  # pragma: no cover - Windows-only dependency
            self.error = str(exc)
            logging.warning("Windows system reminders unavailable: %s", exc)

    def sync(self, tasks: Iterable, now: datetime | None = None) -> int:
        """Replace only this app's future scheduled reminders.

        Rebuilding this small OS schedule after an add/edit/complete action
        prevents stale notifications when a task is moved or deleted.  It does
        not touch notifications from any other application.
        """
        plan = planned_reminders(tasks, now or datetime.now())
        if not self._toaster:
            return 0
        try:
            self._toaster.clear_scheduled_toasts()
            for reminder in plan:
                toast = self._toast_type(
                    [
                        f"{reminder.due_time} · {reminder.title}",
                        "这是一条重要事项提醒，请手动关闭。",
                    ],
                    scenario=self._scenario,
                    # Windows keeps its own notification-center policy. Three
                    # days is its documented maximum/default lifetime.
                    expiration_time=reminder.when + timedelta(days=3),
                )
                # A reminder scenario needs an action to remain a manual
                # reminder rather than becoming an ordinary short toast.
                toast.AddAction(self._dismiss_button_type(self._dismiss_action, "关闭提醒"))
                self._toaster.schedule_toast(toast, reminder.when)
            return len(plan)
        except Exception as exc:  # pragma: no cover - requires Windows shell
            self.error = str(exc)
            logging.warning("Could not schedule Windows system reminders: %s", exc)
            return 0
