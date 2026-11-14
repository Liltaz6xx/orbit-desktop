"""Colours and Qt styles shared by the desktop controls and orb."""

import sys

BG = "#08090B"
TEXT = "#F0F2F5"
MUTED = "#9B9FA7"

STYLESHEET = f"""
    QWidget#Root {{ background: {BG}; color: {TEXT}; }}
    QLabel#Brand {{ color: {TEXT}; font: 600 14px 'Segoe UI'; }}
    QLabel#Version {{ color: {MUTED}; font: 11px 'Segoe UI'; }}
    QLabel#Status {{ color: {TEXT}; font: 600 15px 'Segoe UI'; }}
    QLabel#Detail {{ color: {MUTED}; font: 12px 'Segoe UI'; }}
    QLabel#Subtitle {{ color: {TEXT}; background: #15181D; border: 1px solid #2A2D34;
        border-radius: 10px; padding: 8px 14px; font: 15px 'Segoe UI'; }}
    QLabel#Hint {{ color: {MUTED}; font: 11px 'Segoe UI'; }}
    QFrame#Composer {{ background: #121418; border: 1px solid #2A2D34; border-radius: 22px; }}
    QFrame#Composer[focused="true"] {{ border-color: #616872; }}
    QLineEdit#Entry {{ background: transparent; border: none; color: {TEXT};
        placeholder-text-color: {MUTED}; font: 15px 'Segoe UI'; selection-background-color: #414B5C; }}
    QPushButton#Send {{ background: #E9EDF2; border: 1px solid transparent; border-radius: 16px;
        color: #111317; font: 600 13px 'Segoe UI'; padding: 0 16px; }}
    QPushButton#Send:hover {{ background: #FFFFFF; }}
    QPushButton#Send:pressed {{ background: #C4CAD3; }}
    QPushButton#Send:focus {{ border-color: #666D78; }}
    QPushButton#Send:disabled {{ background: #212429; color: {MUTED}; }}
    QPushButton#HeaderAction {{ color: {TEXT}; background: #15181D; border: 1px solid #353942;
        border-radius: 7px; padding: 5px 8px; font: 12px 'Segoe UI'; }}
    QPushButton#HeaderAction:hover {{ background: #272C34; }}
    QPushButton#HeaderAction:focus {{ border-color: #7B8494; }}
    QPushButton#HeaderAction:disabled {{ color: {MUTED}; }}
    QPushButton#Reply {{ color: {TEXT}; background: transparent; border: none;
        font: 12px 'Segoe UI'; text-decoration: underline; }}
    QPushButton#Reply:hover, QPushButton#Reply:focus {{ color: white; }}
    QDialog {{ background: #14161A; color: {TEXT}; }}
    QDialog QLabel {{ color: {TEXT}; }}
    QDialog QPushButton {{ background: #22262D; color: {TEXT};
        border: 1px solid #3E434D; border-radius: 7px; padding: 6px 18px; }}
    QDialog QPushButton:hover {{ background: #303640; }}
    QDialog QPushButton:focus {{ border-color: #7B8494; }}
    QDialog QTextEdit {{ background: #0C0E11; color: {TEXT}; border: 1px solid #333842;
        border-radius: 8px; padding: 10px; }}
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
