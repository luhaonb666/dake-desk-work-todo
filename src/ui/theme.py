"""Shared V2 visual language for Work Todo's desktop windows."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont, QFontDatabase


def configure_application_font(app) -> str:
    """Choose a crisp installed UI font without bundling a large CJK font."""
    installed = set(QFontDatabase.families())
    if sys.platform == "win32":
        preferred = ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans CN")
    elif sys.platform == "darwin":
        preferred = ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans CN")
    else:
        preferred = ("Noto Sans CJK SC", "Source Han Sans CN", "DejaVu Sans")
    family = next((name for name in preferred if name in installed), app.font().family())
    font = QFont(family, 10)
    font.setWeight(QFont.Weight.Normal)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)
    return family


APP_STYLE = """
    QWidget#root, QDialog { background:#f7f9fc; color:#344054; }
    QLabel { color:#475467; }
    QPushButton {
        background:#ffffff; border:1px solid #d8e1ee; border-radius:10px;
        padding:7px 12px; color:#475467; font-weight:500;
    }
    QPushButton:hover { background:#f1f5ff; border-color:#b8c9eb; }
    QPushButton:pressed { background:#e8eef9; }
    QPushButton#primaryButton {
        background:#4f76e8; color:#ffffff; border:none; font-weight:600;
    }
    QPushButton#primaryButton:hover { background:#4268d7; }
    QPushButton#quietButton {
        border:none; background:transparent; color:#667085; padding:4px 6px;
        font-size:12px; font-weight:500;
    }
    QPushButton#quietButton:hover { background:#edf3ff; color:#3f63c7; }
    QLineEdit, QPlainTextEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox, QSpinBox {
        background:#ffffff; border:1px solid #d8e1ee; border-radius:9px;
        padding:6px 8px; color:#344054; selection-background-color:#b9caf7;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QDateEdit:focus, QTimeEdit:focus, QComboBox:focus, QSpinBox:focus {
        border:2px solid #7f9cf1;
    }
    QComboBox::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {
        border:none; width:24px;
    }
    QCheckBox { color:#475467; spacing:7px; }
    QCheckBox::indicator { width:17px; height:17px; }
    QScrollArea { background:transparent; border:none; }
    QScrollBar:vertical { background:transparent; width:9px; margin:2px; }
    QScrollBar::handle:vertical { background:#cbd5e5; border-radius:4px; min-height:28px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
    QTabBar::tab {
        background:transparent; color:#7a8493; padding:8px 14px;
        border-bottom:2px solid transparent;
    }
    QTabBar::tab:selected { color:#315fc9; border-bottom:2px solid #4f76e8; font-weight:600; }
"""


SETTINGS_STYLE = APP_STYLE + """
    QDialog#settingsDialog { background:#f8fafc; }
    QFrame#settingsSection {
        background:#f4f7fc; border:1px solid #dce6f5; border-radius:14px;
    }
    QLabel#sectionTitle { color:#4771db; font-size:16px; font-weight:600; }
    QLabel#rowLabel { color:#475467; font-size:13px; font-weight:500; }
    QLabel#hintLabel { color:#98a2b3; font-size:11px; }
    QLabel#fixedChip {
        background:#eef2ff; border:1px solid #cbd7fa; border-radius:9px;
        color:#425a9a; padding:7px 10px; font-weight:500;
    }
    QFrame#rowDivider { background:#e5ebf4; border:none; max-height:1px; }
    QPushButton#choiceChip {
        background:#ffffff; border:1px solid #d8e1ee; border-radius:9px;
        padding:7px 9px; color:#475467; font-weight:500;
    }
    QPushButton#choiceChip:checked {
        background:#eef2ff; border:1px solid #aebff2; color:#3f5db5; font-weight:600;
    }
    QPushButton#timeSlotButton {
        background:#ffffff; border:1px solid #d8e1ee; border-radius:9px;
        padding:7px 9px; color:#475467; font-weight:500; text-align:left;
    }
    QPushButton#timeSlotButton:hover { background:#f4f7ff; border-color:#b8c9eb; }
    QPushButton#timeSlotButton[selected="true"] {
        background:#eef2ff; border:1px solid #aebff2; color:#3f5db5; font-weight:600;
    }
    QLabel#easterEgg { color:#9a86bd; font-size:9px; font-weight:400; padding:0; }
    QPushButton#dangerButton { color:#7554be; border-color:#d8cdef; background:#ffffff; }
    QPushButton#dangerButton:hover { background:#f5f0ff; }
"""


TASK_CARD_COLORS = {
    "normal": ("#ffffff", "#dfe6ef"),
    "fixed": ("#edf3ff", "#bfd1f5"),
    "overdue": ("#fff2f2", "#efcaca"),
    "preview": ("#f2f3f5", "#dfe2e6"),
}
