"""Entry point for the native ORBIT application."""

import logging
import sys

from orbit.config import APP_NAME, APP_VERSION, ASSETS, ConfigError, load_settings
from orbit.logging_setup import configure_logging


def main() -> int:
    configure_logging()
    log = logging.getLogger("orbit.startup")
    try:
        from PySide6.QtGui import QFont, QIcon
        from PySide6.QtWidgets import QApplication, QMessageBox
        from orbit.window import OrbitWindow
    except ImportError as exc:
        log.error("event=qt_unavailable package=%s Run Setup_ORBIT.bat.", exc.name or "PySide6")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    icon = ASSETS / "orbit.ico"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    try:
        settings = load_settings()
    except ConfigError as exc:
        log.error("event=config_invalid detail=%s", exc)
        QMessageBox.critical(None, "ORBIT settings", str(exc))
        return 1
    window = OrbitWindow(settings)
    app.aboutToQuit.connect(window.close)
    log.info("event=orbit_started version=%s model=%s", APP_VERSION, settings.model)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
