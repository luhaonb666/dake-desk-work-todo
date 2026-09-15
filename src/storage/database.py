"""SQLite persistence with an explicit schema version."""

from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


class Database:
    SCHEMA_VERSION = 10

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self.connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        version = int(row["value"]) if row else 0
        if version < 1:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    task_date TEXT NOT NULL,
                    due_time TEXT,
                    is_completed INTEGER NOT NULL DEFAULT 0,
                    is_fixed INTEGER NOT NULL DEFAULT 0,
                    float_slot INTEGER,
                    reminded_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date);
                CREATE INDEX IF NOT EXISTS idx_tasks_float_slot ON tasks(float_slot);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            version = 1
        if version < 2:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            for column, definition in (
                ("pre_alerted_at", "TEXT"),
                ("due_alerted_at", "TEXT"),
                ("deleted_at", "TEXT"),
            ):
                if column not in columns:
                    self.connection.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
            # Old manual float slots were internally numbered 4–6. Keep users' choices,
            # but expose the new independent manual slots as 1–3.
            self.connection.execute("UPDATE tasks SET float_slot = float_slot - 3 WHERE float_slot BETWEEN 4 AND 6")
            version = 2
        if version < 3:
            # The first V2 draft stored encouragement text under slots 4–6 while
            # task slots were being renumbered. Preserve it when upgrading to the
            # final, user-facing 1–4 manual slot scheme.
            for old_slot, new_slot in ((4, 1), (5, 2), (6, 3)):
                old_key = f"float_text_{old_slot}"
                new_key = f"float_text_{new_slot}"
                old_row = self.connection.execute(
                    "SELECT value FROM settings WHERE key = ?", (old_key,)
                ).fetchone()
                new_row = self.connection.execute(
                    "SELECT value FROM settings WHERE key = ?", (new_key,)
                ).fetchone()
                if old_row and old_row["value"].strip() and not (new_row and new_row["value"].strip()):
                    self.connection.execute(
                        "INSERT INTO settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (new_key, old_row["value"]),
                    )
            version = 3
        if version < 4:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if "windows_reminder_enabled" not in columns:
                # System notifications are deliberately opt-in. Existing items
                # keep their current float-only reminder behaviour after upgrade.
                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN windows_reminder_enabled INTEGER NOT NULL DEFAULT 0"
                )
            version = 4
        if version < 5:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if "important_acknowledged_at" not in columns:
                self.connection.execute("ALTER TABLE tasks ADD COLUMN important_acknowledged_at TEXT")
            version = 5
        if version < 6:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if "important_snoozed_until" not in columns:
                self.connection.execute("ALTER TABLE tasks ADD COLUMN important_snoozed_until TEXT")
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    is_completed INTEGER NOT NULL DEFAULT 0,
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_task_steps_task_position
                    ON task_steps(task_id, position, id);
                """
            )
            version = 6
        if version < 7:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if "content_mode" not in columns:
                # A task has one primary form of detailed content: normal text
                # or an ordered set of execution steps.  Keep historical text
                # intact during the upgrade, even when an older V4.5 task had
                # both fields filled while this distinction did not yet exist.
                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN content_mode TEXT NOT NULL DEFAULT 'notes'"
                )
            # V4.5 already let a few users add steps beside notes. Preserve
            # that data through the temporary content-mode migration; V4.5.2
            # presents notes and steps together again.
            self.connection.execute(
                "UPDATE tasks SET content_mode = 'steps' "
                "WHERE id IN (SELECT DISTINCT task_id FROM task_steps)"
            )
            version = 7
        if version < 8:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if "important_reminder_offset_minutes" not in columns:
                # Zero preserves every existing opt-in task as a due-time
                # reminder while allowing later versions to trigger earlier.
                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN important_reminder_offset_minutes INTEGER NOT NULL DEFAULT 0"
                )
            version = 8
        if version < 9:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            for column, definition in (
                ("important_repeat_minutes", "INTEGER NOT NULL DEFAULT 0"),
                ("important_repeat_limit", "INTEGER NOT NULL DEFAULT 0"),
                ("important_repeat_count", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in columns:
                    self.connection.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
            version = 9
        if version < 10:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            for column, definition in (
                ("important_reminder_at", "TEXT"),
                ("recurrence_unit", "TEXT NOT NULL DEFAULT 'none'"),
                ("recurrence_interval", "INTEGER NOT NULL DEFAULT 1"),
            ):
                if column not in columns:
                    self.connection.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
            version = 10
        self.connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.connection.commit()

    def ensure_settings_table(self) -> None:
        self.connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.connection.commit()

    def add_task(
        self,
        title: str,
        notes: str,
        task_date: str,
        due_time: str | None,
        is_fixed: bool,
        windows_reminder_enabled: bool = False,
        important_reminder_offset_minutes: int = 0,
        important_reminder_at: str | None = None,
        recurrence_unit: str = "none",
        recurrence_interval: int = 1,
        content_mode: str = "notes",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.connection.execute(
            """INSERT INTO tasks(
                   title, notes, task_date, due_time, is_fixed, windows_reminder_enabled,
                   important_reminder_offset_minutes, important_reminder_at,
                   recurrence_unit, recurrence_interval,
                   content_mode, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title, notes, task_date, due_time, int(is_fixed), int(windows_reminder_enabled),
                max(0, int(important_reminder_offset_minutes)),
                self._normalize_reminder_at(important_reminder_at),
                self._normalize_recurrence_unit(recurrence_unit), max(1, int(recurrence_interval)),
                "steps" if content_mode == "steps" else "notes", now, now,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_task(self, task_id: int, **fields: Any) -> None:
        allowed = {
            "title", "notes", "task_date", "due_time", "is_fixed", "float_slot", "windows_reminder_enabled",
            "important_reminder_offset_minutes", "important_reminder_at",
            "recurrence_unit", "recurrence_interval",
            "content_mode",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if "content_mode" in values:
            values["content_mode"] = "steps" if values["content_mode"] == "steps" else "notes"
        if "important_reminder_offset_minutes" in values:
            values["important_reminder_offset_minutes"] = max(0, int(values["important_reminder_offset_minutes"]))
        if "important_reminder_at" in values:
            values["important_reminder_at"] = self._normalize_reminder_at(values["important_reminder_at"])
        if "recurrence_unit" in values:
            values["recurrence_unit"] = self._normalize_recurrence_unit(values["recurrence_unit"])
        if "recurrence_interval" in values:
            values["recurrence_interval"] = max(1, int(values["recurrence_interval"]))
        if not values:
            return
        # A rescheduled task is a new reminder schedule. Do not clear alert
        # markers merely because an editor submits an unchanged date/time.
        current = self.task_by_id(task_id)
        time_changed = current is not None and (
            ("task_date" in values and values["task_date"] != current["task_date"])
            or ("due_time" in values and values["due_time"] != current["due_time"])
            or (
                "important_reminder_offset_minutes" in values
                and values["important_reminder_offset_minutes"] != current["important_reminder_offset_minutes"]
            )
            or ("important_reminder_at" in values and values["important_reminder_at"] != current["important_reminder_at"])
        )
        if time_changed:
            values["pre_alerted_at"] = None
            values["due_alerted_at"] = None
            values["important_acknowledged_at"] = None
            values["important_snoozed_until"] = None
            values["important_repeat_count"] = 0
        values["updated_at"] = datetime.now().isoformat(timespec="seconds")
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?", (*values.values(), task_id)
        )
        self.connection.commit()

    def clear_float_slot(self, slot: int) -> None:
        self.connection.execute("UPDATE tasks SET float_slot = NULL WHERE float_slot = ?", (slot,))
        self.connection.commit()

    def set_completed(self, task_id: int, completed: bool) -> None:
        now = datetime.now().isoformat(timespec="seconds") if completed else None
        self.connection.execute(
            """UPDATE tasks
               SET is_completed = ?, completed_at = ?,
                   float_slot = CASE WHEN ? = 1 THEN NULL ELSE float_slot END,
                   updated_at = ?
               WHERE id = ?""",
            (int(completed), now, int(completed), datetime.now().isoformat(timespec="seconds"), task_id),
        )
        self.connection.commit()

    @staticmethod
    def _normalize_reminder_at(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return None

    @staticmethod
    def _normalize_recurrence_unit(value: str) -> str:
        return value if value in {"none", "day", "workday", "week", "month", "year"} else "none"

    @staticmethod
    def next_recurrence_date(task_date: str, unit: str, interval: int, today: date | None = None) -> str | None:
        """Return the next usable occurrence date, keeping late completion practical."""
        try:
            current = date.fromisoformat(task_date)
        except ValueError:
            return None
        interval = max(1, int(interval))
        unit = Database._normalize_recurrence_unit(unit)
        if unit == "none":
            return None
        def advance(value: date) -> date:
            if unit == "day":
                return value + timedelta(days=interval)
            if unit == "workday":
                result = value
                remaining = interval
                while remaining:
                    result += timedelta(days=1)
                    if result.weekday() < 5:
                        remaining -= 1
                return result
            if unit == "week":
                return value + timedelta(weeks=interval)
            if unit == "month":
                month_index = value.month - 1 + interval
                year, month = value.year + month_index // 12, month_index % 12 + 1
                return date(year, month, min(value.day, monthrange(year, month)[1]))
            year = value.year + interval
            return date(year, value.month, min(value.day, monthrange(year, value.month)[1]))
        result = advance(current)
        minimum = today or date.today()
        while result < minimum:
            result = advance(result)
        return result.isoformat()

    def create_next_recurrence(self, task_id: int) -> int | None:
        """Create the next occurrence after the current one is completed."""
        task = self.task_by_id(task_id)
        if task is None or not bool(task["is_completed"]):
            return None
        next_date = self.next_recurrence_date(
            task["task_date"], task["recurrence_unit"], task["recurrence_interval"]
        )
        if next_date is None:
            return None
        reminder_at = task["important_reminder_at"] if "important_reminder_at" in task.keys() else None
        if reminder_at:
            try:
                original_reminder = datetime.strptime(reminder_at, "%Y-%m-%d %H:%M")
                original_date = date.fromisoformat(task["task_date"])
                shifted = original_reminder + timedelta(days=(date.fromisoformat(next_date) - original_date).days)
                reminder_at = shifted.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                reminder_at = None
        return self.add_task(
            title=task["title"], notes=task["notes"], task_date=next_date, due_time=task["due_time"],
            is_fixed=bool(task["is_fixed"]), windows_reminder_enabled=bool(task["windows_reminder_enabled"]),
            important_reminder_offset_minutes=int(task["important_reminder_offset_minutes"] or 0),
            important_reminder_at=reminder_at,
            recurrence_unit=task["recurrence_unit"], recurrence_interval=int(task["recurrence_interval"] or 1),
            content_mode=task["content_mode"] if "content_mode" in task.keys() else "notes",
        )

    def delete_task(self, task_id: int) -> None:
        self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.connection.commit()

    def task_steps(self, task_id: int) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT * FROM task_steps WHERE task_id = ?
                   ORDER BY position ASC, id ASC""",
                (task_id,),
            ).fetchall()
        )

    def replace_task_steps(self, task_id: int, steps: Iterable[dict[str, Any]]) -> None:
        """Persist an item's optional, ordered execution steps in one save."""
        cleaned = []
        for step in steps:
            content = str(step.get("content", "")).strip()
            if content:
                cleaned.append((content, int(bool(step.get("is_completed", False)))))
        now = datetime.now().isoformat(timespec="seconds")
        self.connection.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
        self.connection.executemany(
            """INSERT INTO task_steps(task_id, content, is_completed, position, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(task_id, content, completed, position, now, now) for position, (content, completed) in enumerate(cleaned)],
        )
        self.connection.commit()

    def step_summaries(self, task_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
        ids = [int(task_id) for task_id in task_ids]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = self.connection.execute(
            f"""SELECT task_id, SUM(is_completed) AS completed_count, COUNT(*) AS total_count
                FROM task_steps WHERE task_id IN ({placeholders}) GROUP BY task_id""",
            ids,
        ).fetchall()
        return {int(row["task_id"]): (int(row["completed_count"]), int(row["total_count"])) for row in rows}

    def tasks_for(self, task_date: str, pending_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM tasks WHERE task_date = ? AND deleted_at IS NULL"
        args: list[Any] = [task_date]
        if pending_only:
            sql += " AND is_completed = 0"
        sql += " ORDER BY is_fixed ASC, due_time IS NULL ASC, due_time ASC, created_at ASC"
        return list(self.connection.execute(sql, args).fetchall())

    def all_pending_tasks(self) -> list[sqlite3.Row]:
        """Return every unfinished task in calendar order for the scrollable view."""
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE is_completed = 0 AND deleted_at IS NULL
                   ORDER BY task_date ASC, is_fixed ASC, due_time IS NULL ASC, due_time ASC, created_at ASC"""
            ).fetchall()
        )

    def all_tasks(self) -> list[sqlite3.Row]:
        """Return the complete local history, including completed items."""
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE deleted_at IS NULL
                   ORDER BY task_date ASC, is_fixed ASC, due_time IS NULL ASC, due_time ASC, created_at ASC"""
            ).fetchall()
        )

    def fixed_tasks(self) -> list[sqlite3.Row]:
        """Return every item the user marked as a fixed to-do, across dates."""
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE is_fixed = 1 AND deleted_at IS NULL
                   ORDER BY task_date ASC, due_time IS NULL ASC, due_time ASC, created_at ASC"""
            ).fetchall()
        )

    def float_tasks(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM tasks WHERE float_slot IS NOT NULL AND deleted_at IS NULL ORDER BY float_slot"
            ).fetchall()
        )

    def task_by_id(self, task_id: int) -> sqlite3.Row | None:
        """Read one current task row instead of trusting a rendered card copy."""
        return self.connection.execute(
            "SELECT * FROM tasks WHERE id = ? AND deleted_at IS NULL", (task_id,)
        ).fetchone()

    def upcoming_tasks(self, today: str, limit: int = 3) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE task_date = ? AND is_completed = 0 AND is_fixed = 0 AND due_time IS NOT NULL AND deleted_at IS NULL
                   ORDER BY due_time ASC LIMIT ?""",
                (today, limit),
            ).fetchall()
        )

    def mark_reminded(self, task_id: int) -> None:
        self.connection.execute(
            "UPDATE tasks SET reminded_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), task_id),
        )
        self.connection.commit()

    def tasks_needing_reminder(self, today: str) -> Iterable[sqlite3.Row]:
        return self.connection.execute(
            """SELECT * FROM tasks WHERE task_date = ? AND due_time IS NOT NULL
               AND is_completed = 0 AND deleted_at IS NULL""",
            (today,),
        ).fetchall()

    def future_windows_reminder_tasks(self, now: datetime) -> list[sqlite3.Row]:
        """Return only future, unfinished, explicitly opted-in system reminders."""
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE windows_reminder_enabled = 1
                     AND (due_time IS NOT NULL OR important_reminder_at IS NOT NULL)
                     AND is_completed = 0
                     AND deleted_at IS NULL
                   ORDER BY task_date ASC, due_time ASC, created_at ASC"""
            ).fetchall()
        )

    def pending_important_reminder_tasks(self, now: datetime) -> list[sqlite3.Row]:
        """Important due items which have not yet received the user's acknowledgement."""
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE windows_reminder_enabled = 1
                     AND (due_time IS NOT NULL OR important_reminder_at IS NOT NULL)
                     AND is_completed = 0
                     AND important_acknowledged_at IS NULL
                     AND (important_snoozed_until IS NULL OR datetime(important_snoozed_until) <= datetime(?))
                     AND deleted_at IS NULL
                   AND datetime(CASE
                         WHEN important_reminder_at IS NOT NULL THEN important_reminder_at
                         ELSE task_date || ' ' || due_time
                       END, CASE WHEN important_reminder_at IS NOT NULL THEN '+0 minutes'
                                 ELSE '-' || important_reminder_offset_minutes || ' minutes' END) <= datetime(?)
                   ORDER BY task_date ASC, due_time ASC, created_at ASC""",
                (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")),
            ).fetchall()
        )

    def acknowledge_important_reminder(self, task_id: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.connection.execute(
            "UPDATE tasks SET important_acknowledged_at = ?, updated_at = ? WHERE id = ?",
            (now, now, task_id),
        )
        self.connection.commit()

    def snooze_important_reminder(self, task_id: int, minutes: int, now: datetime | None = None) -> None:
        """Hide one important alert briefly without marking its task complete."""
        current = now or datetime.now()
        snoozed_until = current + timedelta(minutes=minutes)
        self.connection.execute(
            "UPDATE tasks SET important_snoozed_until = ?, updated_at = ? WHERE id = ?",
            (snoozed_until.isoformat(timespec="seconds"), current.isoformat(timespec="seconds"), task_id),
        )
        self.connection.commit()

    def mark_alerted(self, task_id: int, kind: str) -> None:
        column = "pre_alerted_at" if kind == "pre" else "due_alerted_at"
        self.connection.execute(
            f"UPDATE tasks SET {column} = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), task_id),
        )
        self.connection.commit()

    @staticmethod
    def today() -> str:
        return date.today().isoformat()
