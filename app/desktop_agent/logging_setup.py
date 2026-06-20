from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_agent_log_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    path = base / "HammerJarvis" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "desktop-agent.log"


def configure_agent_logger() -> logging.Logger:
    logger = logging.getLogger("hammer_jarvis.desktop_agent")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        get_agent_log_path(),
        maxBytes=512_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
