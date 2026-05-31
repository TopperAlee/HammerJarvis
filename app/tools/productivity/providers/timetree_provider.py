from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest


TIMETREE_LIMITED_MESSAGE = (
    "TimeTree ist nur eingeschraenkt vorbereitet. Es wird vorerst als "
    "Import/Export- oder ICS-Quelle behandelt."
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
            "not_supported": True,
            "event": request.__dict__,
            "message": TIMETREE_LIMITED_MESSAGE,
        }

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "limited",
            "message": TIMETREE_LIMITED_MESSAGE,
        }
