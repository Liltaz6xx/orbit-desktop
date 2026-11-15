"""Colours and Qt styles shared by the desktop controls and orb."""

import sys

BG = "#080711"
TEXT = "#F4F0FF"
MUTED = "#BBB4CE"

STYLESHEET = f"""
    QWidget#Root {{ color: {TEXT}; }}
    QLabel#Brand {{ color: {TEXT}; font: 650 19px 'Segoe UI Variable'; }}
    QLabel#Status {{ color: {TEXT}; font: 600 29px 'Segoe UI Variable'; }}
    QLabel#Detail, QLabel#FormHint {{ color: {MUTED}; font: 13px 'Segoe UI'; }}
    QLabel#Subtitle {{ color: {TEXT}; background: rgba(38, 32, 60, 194);
        border: 1px solid rgba(206, 186, 255, 104); border-radius: 15px;
        padding: 8px 16px; font: 16px 'Segoe UI'; }}
    QLabel#Hint {{ color: {MUTED}; font: 11px 'Segoe UI'; padding: 0 3px; }}
    QLineEdit#Entry {{ background: transparent; border: none; color: {TEXT};
        placeholder-text-color: #C0B9D3; font: 16px 'Segoe UI'; selection-background-color: #615488; }}
    QPushButton#Send {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #F5EAFE,stop:1 #C4C8FF);
        border: 1px solid #F1DCFF; border-radius: 14px;
        color: #25183F; font: 600 13px 'Segoe UI'; padding: 0 16px; }}
    QPushButton#Send:hover {{ background: #F9ECFF; }}
    QPushButton#Send:pressed {{ background: #BAB3EC; }}
    QPushButton#Send:focus {{ border-color: #FFFFFF; }}
    QPushButton#Send:disabled {{ background: rgba(98, 89, 138, 104); color: #D5CDE7; border-color: transparent; }}
    QPushButton#HeaderAction, QPushButton#WindowAction {{
        color: {TEXT}; background: rgba(159, 145, 206, 35);
        border: 1px solid rgba(225, 208, 255, 65); border-radius: 11px;
        padding: 5px 8px; font: 12px 'Segoe UI'; }}
    QPushButton#WindowAction {{ padding: 5px; }}
    QPushButton#WindowAction:hover, QPushButton#HeaderAction:hover {{ background: rgba(169, 140, 233, 82); }}
    QPushButton#WindowAction:focus, QPushButton#HeaderAction:focus {{ border-color: #D8C4FF; }}
    QPushButton#HeaderAction:disabled {{ color: {MUTED}; }}
    QWidget#UpdateBanner {{ background: #281F46; border: 1px solid #76649D; border-radius: 13px; }}
    QLabel#UpdateNotice {{ color: #F7EDFF; font: 600 13px 'Segoe UI'; }}
    QPushButton#UpdateAction {{ background: #DAD0FB; color: #261A42; border: 1px solid #EDE2FF;
        border-radius: 8px; padding: 5px 10px; font: 600 12px 'Segoe UI'; }}
    QPushButton#UpdateAction:hover {{ background: #F4E6FF; }}
    QDialog {{ background: #171327; color: {TEXT}; }}
    QDialog QLabel {{ color: {TEXT}; }}
    QDialog QLabel#DialogTitle {{ font: 650 22px 'Segoe UI Variable'; }}
    QDialog QPushButton {{ background: #282139; color: {TEXT};
        border: 1px solid #554669; border-radius: 9px; padding: 7px 15px; }}
    QDialog QPushButton:hover {{ background: #3B2C55; }}
    QDialog QPushButton:focus {{ border-color: #C1A5F2; }}
    QDialog QPushButton:disabled {{ color: #A39AB3; background: #221C30; }}
    QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QTextEdit, QDialog QComboBox {{
        background: #110D20; color: {TEXT}; border: 1px solid #5A4F72;
        border-radius: 9px; padding: 9px; selection-background-color: #655288; }}
    QDialog QCheckBox {{ color: {TEXT}; }}
    QDialog QComboBox QAbstractItemView {{ background: #211932; color: {TEXT};
        selection-background-color: #5F4B83; }}
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
    for attribute, colour in ((34, "#524061"), (35, BG), (36, TEXT)):
        r, g, b = bytes.fromhex(colour[1:])
        value = DWORD(r | (g << 8) | (b << 16))
        set_attribute(hwnd, DWORD(attribute), byref(value), DWORD(sizeof(value)))
