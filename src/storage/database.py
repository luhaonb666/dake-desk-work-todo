"""SQLite persistence with an explicit schema version."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


class Database:
    SCHEMA_VERSION = 1

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
            self.connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(self.SCHEMA_VERSION),),
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
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.connection.execute(
            """INSERT INTO tasks(title, notes, task_date, due_time, is_fixed, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, notes, task_date, due_time, int(is_fixed), now, now),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_task(self, task_id: int, **fields: Any) -> None:
        allowed = {"title", "notes", "task_date", "due_time", "is_fixed", "float_slot"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
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
            "UPDATE tasks SET is_completed = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (int(completed), now, datetime.now().isoformat(timespec="seconds"), task_id),
        )
        self.connection.commit()

    def delete_task(self, task_id: int) -> None:
        self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.connection.commit()

    def tasks_for(self, task_date: str, pending_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM tasks WHERE task_date = ?"
        args: list[Any] = [task_date]
        if pending_only:
            sql += " AND is_completed = 0"
        sql += " ORDER BY is_fixed ASC, due_time IS NULL ASC, due_time ASC, created_at ASC"
        return list(self.connection.execute(sql, args).fetchall())

    def float_tasks(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM tasks WHERE float_slot BETWEEN 4 AND 6 ORDER BY float_slot"
            ).fetchall()
        )

    def upcoming_tasks(self, today: str, limit: int = 3) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT * FROM tasks
                   WHERE task_date = ? AND is_completed = 0 AND is_fixed = 0 AND due_time IS NOT NULL
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
               AND is_completed = 0 AND reminded_at IS NULL""",
            (today,),
        ).fetchall()

    @staticmethod
    def today() -> str:
        return date.today().isoformat()
