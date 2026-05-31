from typing import Any


class CalendarTool:
    def today(self) -> dict[str, Any]:
        return {
            "events": [],
            "message": "Kalender ist vorbereitet, aber noch nicht mit einem echten Konto verbunden.",
        }

    def create_event(
        self,
        title: str | None = None,
        start: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return {
            "confirmation_required": True,
            "title": title,
            "start": start,
            "message": "Ich kann Kalenderfunktionen vorbereiten, aber dein echter Kalender ist noch nicht verbunden.",
        }
