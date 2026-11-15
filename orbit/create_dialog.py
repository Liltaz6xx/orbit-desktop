"""Review the generated output before saving."""

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QLabel, QPlainTextEdit, QVBoxLayout

from .artifacts import ARTIFACT_KINDS, ArtifactError, save_artifact


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
