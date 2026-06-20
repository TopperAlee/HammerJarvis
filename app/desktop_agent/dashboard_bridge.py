from __future__ import annotations

import time
import webbrowser
from typing import Any

import requests

from app.desktop_agent.config import DesktopAgentConfig


class DashboardBridge:
    def __init__(self, config: DesktopAgentConfig) -> None:
        self.config = config
        self.last_browser_open_ms = 0.0

    def status(self) -> dict[str, Any]:
        try:
            response = requests.get(self.config.desktop_status_url, timeout=3)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {"dashboard_clients": 0, "agent_connected": False}

    def heartbeat(self, state: str | dict[str, object] = "READY") -> bool:
        try:
            payload = state if isinstance(state, dict) else {"state": state}
            response = requests.post(self.config.desktop_heartbeat_url, json=payload, timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def open_dashboard_if_needed(self) -> bool:
        if not self.config.open_browser_on_wake:
            return False
        status = self.status()
        if int(status.get("dashboard_clients") or 0) > 0:
            return False
        now_ms = time.monotonic() * 1000
        if now_ms - self.last_browser_open_ms < self.config.wake_cooldown_ms:
            return False
        url = self.config.dashboard_url
        separator = "&" if "?" in url else "?"
        webbrowser.open(f"{url}{separator}source=desktop-agent")
        self.last_browser_open_ms = now_ms
        return True

    def wait_for_dashboard(self) -> bool:
        deadline = time.monotonic() + self.config.dashboard_timeout_seconds
        while time.monotonic() < deadline:
            if int(self.status().get("dashboard_clients") or 0) > 0:
                return True
            time.sleep(0.5)
        return False

    def send_wake_event(self, event: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self.config.desktop_wake_url, json=event, timeout=5)
        response.raise_for_status()
        return response.json()
