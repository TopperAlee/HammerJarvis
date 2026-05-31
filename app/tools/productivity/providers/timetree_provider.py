from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest


TIMETREE_LIMITED_MESSAGE = (
    "TimeTree wird vorerst nur als Import/Export- oder ICS-Quelle vorbereitet, "
    "da die oeffentliche Entwickler-API nicht mehr regulaer verfuegbar ist."
)


class TimeTreeProvider:
    name = "timetree"

    def list_events(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "limited",
            "events": [],
            "message": TIMETREE_LIMITED_MESSAGE,
        }

    def create_event(self, request: CalendarEventCreateRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "limited",
            "blocked": True,
            "event": request.__dict__,
            "message": TIMETREE_LIMITED_MESSAGE,
        }

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "limited",
            "message": TIMETREE_LIMITED_MESSAGE,
        }
