"""Edit the local assistant profile from the desktop window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from .preferences import Preferences, STYLES, VOICES, save_preferences


class SettingsDialog(QDialog):
    def __init__(self, preferences, parent):
        super().__init__(parent)
        self.setWindowTitle("ORBIT settings")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(preferences.name)
        self.name.setMaxLength(24)
        self.voice = QComboBox()
        for key, label in VOICES.items():
            self.voice.addItem(label, key)
        self.voice.setCurrentIndex(self.voice.findData(preferences.voice))
        self.style = QComboBox()
        self.style.addItems(list(STYLES))
        self.style.setCurrentText(preferences.style)
        self.listening = QCheckBox("Listen for “Hey” followed by the assistant name")
        self.listening.setChecked(preferences.listening)
        self.macros = QPlainTextEdit()
        self.macros.setPlainText("\n".join(
            f"{name} = {' | '.join(commands)}" for name, commands in preferences.macros.items()
        ))
        self.macros.setPlaceholderText("work = open Notepad | open Documents folder")
        form.addRow("Assistant name", self.name)
        form.addRow("Voice", self.voice)
        form.addRow("Personality", self.style)
        form.addRow("Microphone", self.listening)
        form.addRow("Macros", self.macros)
        layout.addLayout(form)
        hint = QLabel("Enter one macro per line, using | between steps. Type or say “run macro work” to run the example.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(480, self.sizeHint().height())

    def save(self):
        try:
            macros = {}
            for line in self.macros.toPlainText().splitlines():
                if not line.strip():
                    continue
                name, delimiter, commands = line.partition("=")
                name = " ".join(name.casefold().split())
                if not delimiter or name in macros:
                    raise ValueError("Use a unique name and an equals sign for each macro.")
                macros[name] = tuple(command.strip() for command in commands.split("|"))
            self.preferences = Preferences(self.name.text().strip(), self.voice.currentData(),
                                           self.style.currentText(), self.listening.isChecked(), macros)
            save_preferences(self.preferences)
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc) if isinstance(exc, ValueError) else "Could not save your local settings.")
            return
        self.accept()
