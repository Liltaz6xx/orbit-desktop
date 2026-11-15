"""Search and read conversations saved in the local ORBIT archive."""

import sqlite3
from datetime import datetime, timezone
from html import escape

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
)

from .memory import MemoryStore

PAGE_SIZE = 40
STYLE = """
QDialog#History { background: #0D141C; }
QDialog#History QLabel { color: #E8F0F6; font: 13px 'Segoe UI'; }
QDialog#History QLabel#Title { color: #F2FAFD; font: 600 25px 'Segoe UI'; }
QDialog#History QLabel#Summary { color: #A9BCC9; }
QDialog#History QLineEdit, QDialog#History QListWidget, QDialog#History QTextBrowser {
    color: #E8F0F6; background: #131E29; border: 1px solid #2A3D4E;
    border-radius: 9px; font: 14px 'Segoe UI'; selection-background-color: #234E55;
}
QDialog#History QLineEdit { padding: 8px 12px; }
QDialog#History QLineEdit:focus { border-color: #76D8CA; }
QDialog#History QTextBrowser { padding: 12px; }
QDialog#History QListWidget { padding: 5px; }
QDialog#History QListWidget::item { padding: 6px 9px; border-radius: 5px; }
QDialog#History QListWidget::item:hover { background: #1D3040; }
QDialog#History QListWidget::item:selected { background: #234E55; color: #F4FDFF; }
QDialog#History QPushButton { color: #E8F0F6; background: #182634; border: 1px solid #344A5C;
    border-radius: 7px; padding: 7px 12px; font: 13px 'Segoe UI'; }
QDialog#History QPushButton:hover { background: #243B4D; }
QDialog#History QPushButton:focus { border-color: #76D8CA; }
QDialog#History QPushButton:disabled { color: #8195A5; border-color: #253642; }
QDialog#History QPushButton#ClearHistory { color: #FFD0D0; }
"""


def local_timestamp(stamp):
    try:
        local = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return "Unknown time"
    if local.tzinfo is None:
        local = local.replace(tzinfo=timezone.utc)
    return local.astimezone().strftime("%d %b %Y · %H:%M")


class HistoryDialog(QDialog):
    def __init__(self, database_path, parent=None):
        super().__init__(parent)
        self.database_path = database_path
        self.rows = []
        self.query = ""
        self.setObjectName("History")
        self.setWindowTitle("Chat history")
        self.resize(810, 560)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 19, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Chat history", objectName="Title"))
        self.search = QLineEdit(placeholderText="Search conversations")
        self.search.setAccessibleName("Search conversations")
        self.search.setMaxLength(200)
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.conversations = QListWidget()
        self.conversations.setAccessibleName("Saved conversations")
        self.conversations.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conversations.currentRowChanged.connect(self.show_turn)
        self.transcript = QTextBrowser()
        self.transcript.setAccessibleName("Selected conversation")
        self.transcript.setOpenLinks(False)
        split.addWidget(self.conversations)
        split.addWidget(self.transcript)
        split.setSizes([250, 520])
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

        footer = QHBoxLayout()
        self.summary = QLabel(objectName="Summary")
        footer.addWidget(self.summary)
        footer.addStretch()
        self.more = QPushButton("Load older")
        self.more.clicked.connect(self.load_older)
        self.copy = QPushButton("Copy exchange")
        self.copy.clicked.connect(self.copy_turn)
        self.clear = QPushButton("Clear history", objectName="ClearHistory")
        self.clear.clicked.connect(self.clear_history)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for button in (self.more, self.copy, self.clear, close):
            button.setAutoDefault(False)
            footer.addWidget(button)
        layout.addLayout(footer)

        self.delay = QTimer(self, interval=180, singleShot=True)
        self.delay.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.delay.start())
        self.refresh()
        self.search.setFocus()

    def refresh(self):
        selected = self.current_turn()
        self.query = self.search.text().strip()
        self.rows.clear()
        self.conversations.clear()
        self.transcript.clear()
        self.copy.setEnabled(False)
        self.clear.setEnabled(False)
        self.more.hide()
        if self.load_page() and self.rows:
            selected_id = selected["id"] if selected else None
            index = next((i for i, row in enumerate(self.rows) if row["id"] == selected_id), 0)
            self.conversations.setCurrentRow(index)

    def load_older(self):
        if self.rows:
            first_new_row = len(self.rows)
            if self.load_page(self.rows[-1]["id"]) and first_new_row < len(self.rows):
                self.conversations.setCurrentRow(first_new_row)

    def load_page(self, before=None):
        try:
            rows = MemoryStore.history_page(
                self.database_path, self.query, before=before, limit=PAGE_SIZE + 1,
            )
        except (sqlite3.Error, OSError):
            self.summary.setText("Could not read history.")
            if before is None:
                self.transcript.setPlainText("The local archive could not be opened.")
            return False
        for row in rows[:PAGE_SIZE]:
            preview = " ".join(row["user_text"].split())
            if len(preview) > 34:
                preview = preview[:33].rstrip() + "…"
            item = QListWidgetItem(f"{preview}\n{local_timestamp(row['created_at'])}")
            item.setToolTip(f"<span>{escape(preview)}</span>")
            item.setSizeHint(QSize(175, 57))
            self.conversations.addItem(item)
            self.rows.append(row)
        if not self.rows:
            empty = "No matches" if self.query else "No saved conversations"
            self.summary.setText(empty)
            self.transcript.setPlainText(
                "Try a different search." if self.query else "Completed conversations will appear here."
            )
        else:
            total = len(self.rows)
            noun = ("match" if total == 1 else "matches") if self.query else ("exchange" if total == 1 else "exchanges")
            self.summary.setText(f"{total} {noun} shown")
            self.clear.setEnabled(True)
        self.more.setVisible(len(rows) > PAGE_SIZE)
        return True

    def current_turn(self):
        index = self.conversations.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def show_turn(self, _index):
        row = self.current_turn()
        self.copy.setEnabled(row is not None)
        if row is None:
            return
        stamp = local_timestamp(row["created_at"])
        markup = [f'<p style="color:#A9BCC9;font-size:12px;">{stamp}</p>']
        for label, color, text in (
            ("You", "#9FBAE1", row["user_text"]),
            ("Assistant", "#8DDDD0", row["assistant_text"]),
        ):
            content = escape(text).replace("\n", "<br>")
            markup.append(f'<p style="margin-top:22px;margin-bottom:5px;color:{color};">'
                          f'<b>{label}</b></p><p style="color:#E8F0F6;">{content}</p>')
        self.transcript.setHtml("".join(markup))

    def copy_turn(self):
        row = self.current_turn()
        if row:
            clipboard = QApplication.clipboard()
            clipboard.setText(f"You\n{row['user_text']}\n\nAssistant\n{row['assistant_text']}")
            self.summary.setText("Exchange copied")

    def clear_history(self):
        yes = QMessageBox.StandardButton.Yes
        confirm = QMessageBox.question(
            self, "Clear chat history?",
            "Delete all saved conversations from this computer? Saved memory notes will be kept.",
            yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if confirm != yes:
            return
        try:
            MemoryStore(self.database_path).clear_conversations()
        except (sqlite3.Error, OSError):
            QMessageBox.warning(self, "Chat history", "Could not clear the local archive. Try again.")
            return
        self.search.clear()
        self.delay.stop()
        self.refresh()
