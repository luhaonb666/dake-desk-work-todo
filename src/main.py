"""DaKe Desk V4.5 application entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from app_paths import configure_logging
from services.hotkey import GlobalHotkey
from ui.main_window import MainWindow, app_icon
from ui.theme import configure_application_font


def install_exception_hook() -> None:
    def report_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.critical("Unhandled exception\n%s", details)
        QMessageBox.critical(None, "大可桌边发生错误", "程序出现异常，详细原因已写入日志。")

    sys.excepthook = report_exception


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--background", action="store_true")
    args, _ = parser.parse_known_args()
    configure_logging()
    install_exception_hook()
    app = QApplication(sys.argv)
    configure_application_font(app)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    hotkey = GlobalHotkey(window.show_editor)
    app.installNativeEventFilter(hotkey)
    window.set_hotkey_manager(hotkey)
    shortcut = window.db.get_setting("float_shortcut", "none")
    if shortcut != "none" and not hotkey.register(shortcut):
        logging.warning("Configured global shortcut was not available")
    if args.background:
        window.hide()
    else:
        window.show_editor()
    exit_code = app.exec()
    hotkey.unregister()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
