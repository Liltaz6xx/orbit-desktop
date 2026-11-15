"""Compose a local file request and review the generated output before saving."""

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .artifacts import ARTIFACT_KINDS, SOURCE_SUFFIXES, ArtifactError, ArtifactRequest, load_source, save_artifact


class CreateDialog(QDialog):
    def __init__(self, parent=None, kind=None, prompt=""):
        super().__init__(parent)
        self.setWindowTitle("Create with ORBIT")
        self.source = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(11)
        layout.addWidget(QLabel("Create with ORBIT", objectName="DialogTitle"))
        form = QFormLayout()
        self.kind = QComboBox()
        for value, label in ARTIFACT_KINDS.items():
            self.kind.addItem(label, value)
        if kind is not None:
            self.kind.setCurrentIndex(self.kind.findData(kind))
        form.addRow("Format", self.kind)
        self.prompt = QPlainTextEdit(prompt)
        self.prompt.setPlaceholderText("Describe what to make, who it is for, and what to include.")
        self.prompt.setMinimumHeight(132)
        form.addRow("Instructions", self.prompt)
        layout.addLayout(form)

        source_row = QHBoxLayout()
        attach = QPushButton("Attach notes")
        attach.clicked.connect(self.attach_source)
        self.source_name = QLabel("Optional", objectName="FormHint")
        self.source_name.setTextFormat(Qt.TextFormat.PlainText)
        self.source_name.setWordWrap(True)
        self.remove = QPushButton("Remove")
        self.remove.clicked.connect(self.clear_source)
        self.remove.hide()
        source_row.addWidget(attach)
        source_row.addWidget(self.source_name, 1)
        source_row.addWidget(self.remove)
        layout.addLayout(source_row)
        self.error = QLabel(objectName="FormHint")
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        create = buttons.addButton("Generate draft", QDialogButtonBox.ButtonRole.AcceptRole)
        create.clicked.connect(self.accept_request)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 345)

    def attach_source(self):
        patterns = " ".join(f"*{suffix}" for suffix in SOURCE_SUFFIXES)
        filename, _ = QFileDialog.getOpenFileName(
            self, "Attach local notes", "", f"Supported notes ({patterns})"
        )
        if not filename:
            return
        try:
            text = load_source(Path(filename))
        except (OSError, ValueError, ArtifactError) as exc:
            self.error.setText(str(exc))
            return
        self.source = text
        self.source_name.setText(Path(filename).name)
        self.remove.show()
        self.error.clear()

    def clear_source(self):
        self.source = ""
        self.source_name.setText("Optional")
        self.remove.hide()
        self.error.clear()

    def accept_request(self):
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.error.setText("Describe what you want ORBIT to make.")
            return
        if len(prompt) > 2000:
            self.error.setText("Keep instructions within 2,000 characters. Attach longer source notes separately.")
            return
        try:
            self.request = ArtifactRequest(self.kind.currentData(), prompt, self.source)
        except (ValueError, ArtifactError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class ArtifactReview(QDialog):
    def __init__(self, artifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setWindowTitle("Review draft")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        title = QLabel(artifact.title, objectName="DialogTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        preview = QPlainTextEdit(artifact.preview)
        preview.setReadOnly(True)
        preview.setAccessibleName("Draft preview")
        layout.addWidget(preview, 1)
        self.status = QLabel(objectName="FormHint")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        save = buttons.addButton("Save as…", QDialogButtonBox.ButtonRole.ActionRole)
        save.clicked.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(650, 500)

    def save(self):
        artifact = self.artifact
        target = QDir.home().filePath(artifact.filename)
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save ORBIT draft", target, f"{ARTIFACT_KINDS[artifact.kind]} (*{artifact.extension})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(artifact.extension)
        try:
            location = save_artifact(artifact, path)
        except (OSError, ValueError, ArtifactError) as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(f"Saved to {location}")
