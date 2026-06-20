from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self, name: str = r"Local\HammerJarvisDesktopAgent", lock_path: Path | None = None) -> None:
        self.name = name
        self.lock_path = lock_path
        self._handle: int | None = None
        self._lock_file = None

    def acquire(self, logger: logging.Logger | None = None) -> bool:
        if sys.platform.startswith("win"):
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, self.name)
            if not handle:
                if logger:
                    logger.error("single_instance_mutex_failed")
                return False
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                if logger:
                    logger.info("single_instance_second_instance_exit")
                return False
            self._handle = handle
            return True
        path = self.lock_path or Path.home() / ".hammer_jarvis_desktop_agent.lock"
        try:
            self._lock_file = path.open("x", encoding="utf-8")
            self._lock_file.write(str(Path.cwd()))
            self._lock_file.flush()
            return True
        except FileExistsError:
            if logger:
                logger.info("single_instance_lock_exists")
            return False

    def release(self) -> None:
        if self._handle and sys.platform.startswith("win"):
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._lock_file:
            path = Path(self._lock_file.name)
            self._lock_file.close()
            try:
                path.unlink()
            except OSError:
                pass
            self._lock_file = None
