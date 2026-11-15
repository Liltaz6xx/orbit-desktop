"""Colours and Qt styles shared by the desktop controls and orb."""

import sys

BG = "#0B1017"
TEXT = "#E9F1F5"
MUTED = "#A1B0BE"

STYLESHEET = f"""
    QWidget#Root {{ background: {BG}; color: {TEXT}; }}
    QFrame#Toolbar {{ background: #111923; border: 1px solid #263544; border-radius: 12px; }}
    QLabel#Brand {{ color: {TEXT}; font: 650 19px 'Segoe UI'; }}
    QLabel#Status {{ color: {TEXT}; font: 600 25px 'Segoe UI'; }}
    QLabel#Detail {{ color: {MUTED}; font: 13px 'Segoe UI'; }}
    QLabel#Subtitle {{ color: {TEXT}; background: #141F2A; border: 1px solid #34505D;
        border-radius: 12px; padding: 8px 16px; font: 15px 'Segoe UI'; }}
    QLabel#Hint {{ color: {MUTED}; font: 11px 'Segoe UI'; padding: 0 3px; }}
    QFrame#Composer {{ background: #131C26; border: 1px solid #304151; border-radius: 16px; }}
    QFrame#Composer[focused="true"] {{ border-color: #69A5A0; }}
    QLineEdit#Entry {{ background: transparent; border: none; color: {TEXT};
        placeholder-text-color: {MUTED}; font: 15px 'Segoe UI'; selection-background-color: #414B5C; }}
    QPushButton#Send {{ background: #9FE2D3; border: 1px solid transparent; border-radius: 10px;
        color: #0A2325; font: 600 13px 'Segoe UI'; padding: 0 16px; }}
    QPushButton#Send:hover {{ background: #B8F2E5; }}
    QPushButton#Send:pressed {{ background: #87CDBD; }}
    QPushButton#Send:focus {{ border-color: #F0F7FA; }}
    QPushButton#Send:disabled {{ background: #24323E; color: {MUTED}; }}
    QPushButton#HeaderAction {{ color: {TEXT}; background: #192430; border: 1px solid #324351;
        border-radius: 7px; padding: 6px 8px; font: 12px 'Segoe UI'; }}
    QPushButton#HeaderAction:hover {{ background: #243644; }}
    QPushButton#HeaderAction:focus {{ border-color: #87CDBD; }}
    QPushButton#HeaderAction:disabled {{ color: {MUTED}; }}
    QPushButton#Reply {{ color: {TEXT}; background: transparent; border: none;
        font: 12px 'Segoe UI'; text-decoration: underline; }}
    QPushButton#Reply:hover, QPushButton#Reply:focus {{ color: white; }}
    QDialog {{ background: #111923; color: {TEXT}; }}
    QDialog QLabel {{ color: {TEXT}; }}
    QDialog QPushButton {{ background: #22262D; color: {TEXT};
        border: 1px solid #3E434D; border-radius: 7px; padding: 6px 18px; }}
    QDialog QPushButton:hover {{ background: #303640; }}
    QDialog QPushButton:focus {{ border-color: #7B8494; }}
    QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QTextEdit, QDialog QComboBox {{
        background: #0D141D; color: {TEXT}; border: 1px solid #354756;
        border-radius: 8px; padding: 10px; }}
    QDialog QCheckBox {{ color: {TEXT}; }}
    QDialog QComboBox QAbstractItemView {{ background: #192430; color: {TEXT};
        selection-background-color: #304A57; }}
"""


def apply_window_frame(widget):
    if sys.platform != "win32":
        return
    from ctypes import WinDLL, byref, sizeof
    from ctypes.wintypes import DWORD, HWND

    try:
        set_attribute = WinDLL("dwmapi").DwmSetWindowAttribute
    except (OSError, AttributeError):
        return
    hwnd = HWND(int(widget.winId()))
    for attribute, colour in ((34, "#292C32"), (35, BG), (36, TEXT)):
        r, g, b = bytes.fromhex(colour[1:])
        value = DWORD(r | (g << 8) | (b << 16))
        set_attribute(hwnd, DWORD(attribute), byref(value), DWORD(sizeof(value)))
