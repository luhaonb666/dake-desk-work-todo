"""DaKe Desk V4.7.4 application entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QMessageBox

from app_paths import begin_session, configure_logging, finish_session
from services.hotkey import GlobalHotkey
from ui.main_window import MainWindow, app_icon
from ui.theme import configure_application_font


APP_VERSION = "4.7.4"


def install_exception_hook() -> None:
    def report_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.critical("Unhandled exception\n%s", details)
        QMessageBox.critical(None, "大可桌边发生错误", "程序出现异常，详细原因已写入日志。")

    sys.excepthook = report_exception


def install_qt_message_handler() -> None:
    """Persist Qt warnings that otherwise disappear in windowed builds."""
    levels = {
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def report_qt_message(mode, context, message) -> None:
        level = levels.get(mode)
        if level is None:
            return
        location = f" {context.file}:{context.line}" if context.file else ""
        logging.log(level, "Qt message%s: %s", location, message)

    qInstallMessageHandler(report_qt_message)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--safe-mode", action="store_true")
    args, _ = parser.parse_known_args()
    configure_logging()
    install_exception_hook()
    install_qt_message_handler()
    previous_crash = begin_session(APP_VERSION)
    if previous_crash:
        logging.warning("Previous session ended unexpectedly; entering recovery mode")
    app = QApplication(sys.argv)
    configure_application_font(app)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(recovery_mode=args.safe_mode or previous_crash)
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
    app.aboutToQuit.connect(finish_session)
    exit_code = app.exec()
    finish_session()
    hotkey.unregister()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
