"""Stable, user-writable locations for application data and logs."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


APP_NAME = "大可桌边"
# Keep this folder name stable. Existing users already have their database under
# %LOCALAPPDATA%\WorkTodo, so changing it would make an upgrade appear empty.
DATA_FOLDER_NAME = "WorkTodo"


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
