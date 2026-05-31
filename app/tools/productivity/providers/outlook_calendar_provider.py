from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest


class OutlookCalendarProvider:
    name = "outlook_calendar"

    def list_today_events(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "events": [],
            "message": "Outlook Kalender ist vorbereitet, aber Microsoft Graph OAuth ist noch nicht verbunden.",
        }

    def create_event(self, request: CalendarEventCreateRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "confirmation_required": True,
            "event": request.__dict__,
            "message": "Microsoft Graph OAuth fuer Outlook Kalender ist noch nicht verbunden. Es wurde kein echter Termin erstellt.",
        }
