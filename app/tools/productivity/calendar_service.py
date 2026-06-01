from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest
from app.tools.productivity.providers.google_calendar_provider import GoogleCalendarProvider
from app.tools.productivity.providers.outlook_calendar_provider import OutlookCalendarProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider


class CalendarService:
    def __init__(self) -> None:
        self.providers = {
            "outlook_calendar": OutlookCalendarProvider(),
            "google_calendar": GoogleCalendarProvider(),
            "timetree": TimeTreeProvider(),
        }

    def list_today_events(self, providers: list[str] | None = None) -> dict[str, Any]:
        selected = providers or ["outlook_calendar"]
        results: list[dict[str, Any]] = []
        for provider in selected:
            if provider == "timetree":
                results.append(self.providers[provider].list_today_events())
            elif provider in self.providers:
                results.append(self.providers[provider].list_today_events())
        return {
            "providers": results,
            "message": (
                "Ich kann deine Termine grundsaetzlich aus Outlook lesen, aber "
                "Outlook ist noch nicht verbunden. Die Kalender-Schnittstelle "
                "ist vorbereitet."
            ),
        }

    def create_event(
        self,
        provider: str = "outlook_calendar",
        request: CalendarEventCreateRequest | None = None,
    ) -> dict[str, Any]:
        event = request or CalendarEventCreateRequest(title="", start="")
        selected = provider if provider in self.providers else "outlook_calendar"
        if selected == "timetree":
            return self.providers[selected].create_event(event)
        return self.providers[selected].create_event(event)

    def timetree_status(self) -> dict[str, Any]:
        return self.providers["timetree"].status()
