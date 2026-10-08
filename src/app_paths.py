"""Stable, user-writable locations for application data and logs."""

from __future__ import annotations

import logging
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


APP_NAME = "大可桌边"
# Keep this folder name stable. Existing users already have their database under
# %LOCALAPPDATA%\WorkTodo, so changing it would make an upgrade appear empty.
DATA_FOLDER_NAME = "WorkTodo"
SESSION_MARKER_NAME = "session-active"
LAST_ACTION_NAME = "last-action.txt"
QUARANTINE_NAME = "quarantined-tasks.json"


def app_data_dir() -> Path:
    """Return a per-user writable directory, never the executable directory."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = root / DATA_FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging() -> Path:
    """Configure a rotating-enough plain file log for support diagnostics."""
    log_path = app_data_dir() / "work-todo.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return log_path


def session_marker_path() -> Path:
    """Return the marker left behind when a process exits unexpectedly."""
    return app_data_dir() / SESSION_MARKER_NAME


def begin_session(version: str) -> bool:
    """Mark a running session and report whether the previous one crashed."""
    marker = session_marker_path()
    previous_crash = marker.exists()
    marker.write_text(
        f"version={version}\nstarted={datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )
    return previous_crash


def finish_session() -> None:
    """Remove the marker after a normal Qt shutdown."""
    try:
        session_marker_path().unlink(missing_ok=True)
    except OSError:
        logging.exception("Could not clear the session marker")


def record_last_action(action: str) -> None:
    """Keep a privacy-safe description of the last UI action for crash triage."""
    try:
        (app_data_dir() / LAST_ACTION_NAME).write_text(
            f"{datetime.now().isoformat(timespec='seconds')} {action}\n",
            encoding="utf-8",
        )
    except OSError:
        logging.exception("Could not record the last UI action")


def load_quarantined_tasks() -> dict[str, str]:
    """Load task ids hidden after a crash-triggering UI action."""
    path = app_data_dir() / QUARANTINE_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def quarantine_task_from_last_action() -> int | None:
    """Remember the task involved in the last action after an abnormal exit."""
    marker = session_marker_path()
    if not marker.exists():
        return None
    try:
        action = (app_data_dir() / LAST_ACTION_NAME).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(?:task|id)=(\d+)", action)
    if not match:
        return None
    task_id = int(match.group(1))
    quarantined = load_quarantined_tasks()
    quarantined[str(task_id)] = action.strip()
    try:
        (app_data_dir() / QUARANTINE_NAME).write_text(
            json.dumps(quarantined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logging.exception("Could not save quarantined task %s", task_id)
    return task_id


def remove_quarantined_task(task_id: int) -> None:
    """Forget a quarantined id after the user removes the problematic item."""
    quarantined = load_quarantined_tasks()
    quarantined.pop(str(int(task_id)), None)
    path = app_data_dir() / QUARANTINE_NAME
    try:
        if quarantined:
            path.write_text(
                json.dumps(quarantined, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)
    except OSError:
        logging.exception("Could not remove quarantined task %s", task_id)
