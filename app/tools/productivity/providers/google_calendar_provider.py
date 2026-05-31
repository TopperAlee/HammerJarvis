from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest


class GoogleCalendarProvider:
    name = "google_calendar"

    def list_today_events(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "events": [],
            "message": "Google Calendar ist vorbereitet, aber Google OAuth ist noch nicht verbunden.",
        }

    def create_event(self, request: CalendarEventCreateRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "confirmation_required": True,
            "event": request.__dict__,
            "message": "Google Calendar OAuth ist noch nicht verbunden. Es wurde kein echter Termin erstellt.",
        }
