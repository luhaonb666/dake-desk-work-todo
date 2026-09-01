"""A Windows RegisterHotKey bridge correctly connected to Qt's native event filter."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001


class GlobalHotkey(QAbstractNativeEventFilter):
    """Register Alt+E on Windows and dispatch its native message into Qt."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self.callback = callback
        self.hotkey_id = 31415
        self.registered = False

    def register(self, shortcut: str = "none") -> bool:
        self.unregister()
        if sys.platform != "win32" or shortcut.lower() == "none":
            return False
        if shortcut.lower() != "alt+e":
            logging.warning("Unsupported shortcut requested: %s", shortcut)
            return False
        result = ctypes.windll.user32.RegisterHotKey(None, self.hotkey_id, MOD_ALT, ord("E"))
        self.registered = bool(result)
        if not self.registered:
            logging.warning("Alt+E could not be registered; another application may own it")
        return self.registered

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, self.hotkey_id)
            self.registered = False

    def nativeEventFilter(self, event_type, message):  # type: ignore[override]
        if sys.platform != "win32":
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                self.callback()
                return True, 0
        except (TypeError, ValueError, OSError):
            logging.exception("Unable to process native hotkey message")
        return False, 0
