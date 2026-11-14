"""Local diagnostic logging with bounded retention."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR


def configure_logging() -> None:
    logger = logging.getLogger("orbit")
    if logger.handlers:
        return
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        file = RotatingFileHandler(
            DATA_DIR / "orbit.log", maxBytes=512_000, backupCount=3, encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("event=log_file_unavailable error=%s", type(exc).__name__)
    else:
        file.setFormatter(formatter)
        logger.addHandler(file)
