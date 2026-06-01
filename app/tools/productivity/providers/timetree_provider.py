import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from app.tools.productivity.models import CalendarEventCreateRequest


TIMETREE_DISABLED_MESSAGE = (
    "TimeTree ist vorbereitet, aber der lokale ICS-Import ist deaktiviert."
)
TIMETREE_CREATE_BLOCKED_MESSAGE = (
    "TimeTree-Events koennen ueber Hammer Jarvis nicht erstellt werden. "
    "TimeTree wird nur als ICS-Lesequelle unterstuetzt."
)


class TimeTreeProvider:
    name = "timetree"

    def status(self) -> dict[str, Any]:
        if not self._enabled():
            return {
                "provider": self.name,
                "enabled": False,
                "connected": "limited",
                "message": TIMETREE_DISABLED_MESSAGE,
            }

        ics_file = self._ics_file()
        if not ics_file.is_file():
            return {
                "provider": self.name,
                "enabled": True,
                "connected": False,
                "events": [],
                "message": "TimeTree ICS-Datei wurde nicht gefunden.",
            }

        return {
            "provider": self.name,
            "enabled": True,
            "connected": True,
            "source": "ics",
            "message": "TimeTree ICS-Import ist aktiviert.",
        }

    def list_events(self) -> dict[str, Any]:
        if not self._enabled():
            return {**self.status(), "events": []}

        ics_file = self._ics_file()
        if not ics_file.is_file():
            return self.status()

        try:
            events = self._parse_ics_file(ics_file)
        except Exception:
            return {
                "provider": self.name,
                "enabled": True,
                "connected": False,
                "error": True,
                "events": [],
                "message": "Die TimeTree ICS-Datei konnte nicht gelesen werden.",
            }

        return {
            "provider": self.name,
            "enabled": True,
            "connected": True,
            "source": "ics",
            "events": events,
            "count": len(events),
            "message": f"Es wurden {len(events)} TimeTree-Termine gefunden.",
        }

    def list_today_events(self) -> dict[str, Any]:
        events_result = self.list_events()
        if events_result.get("enabled") is not True or events_result.get("error"):
            return events_result
        if events_result.get("connected") is not True:
            return events_result

        today = date.today()
        events = [
            event
            for event in events_result.get("events", [])
            if self._event_overlaps_day(event, today)
        ]
        return {
            "provider": self.name,
            "enabled": True,
            "connected": True,
            "source": "ics",
            "events": events,
            "count": len(events),
            "message": f"Heute wurden {len(events)} TimeTree-Termine gefunden.",
        }

    def create_event(self, request: CalendarEventCreateRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "blocked": True,
            "status": "not_supported",
            "event": request.__dict__,
            "message": TIMETREE_CREATE_BLOCKED_MESSAGE,
        }

    def _enabled(self) -> bool:
        return os.getenv("TIMETREE_ENABLED", "false").strip().lower() == "true"

    def _ics_file(self) -> Path:
        return Path(
            os.getenv("TIMETREE_ICS_FILE", "app/data/timetree/timetree.ics")
        )

    def _parse_ics_file(self, ics_file: Path) -> list[dict[str, Any]]:
        content = ics_file.read_text(encoding="utf-8")
        if "BEGIN:VCALENDAR" not in content or "BEGIN:VEVENT" not in content:
            raise ValueError("invalid ics")

        try:
            return self._parse_with_icalendar(content)
        except ModuleNotFoundError:
            return self._parse_minimal_ics(content)

    def _parse_with_icalendar(self, content: str) -> list[dict[str, Any]]:
        from icalendar import Calendar

        calendar = Calendar.from_ical(content)
        events: list[dict[str, Any]] = []
        for component in calendar.walk("VEVENT"):
            start_value = component.get("DTSTART")
            if not start_value:
                continue
            start = start_value.dt
            end_value = component.get("DTEND")
            end = end_value.dt if end_value else start
            events.append(
                self._event_dict(
                    title=str(component.get("SUMMARY", "")),
                    start=start,
                    end=end,
                    location=str(component.get("LOCATION", "")) or None,
                    description=str(component.get("DESCRIPTION", "")) or None,
                )
            )
        return events

    def _parse_minimal_ics(self, content: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for block in content.split("BEGIN:VEVENT")[1:]:
            event_text = block.split("END:VEVENT", 1)[0]
            fields = self._parse_event_fields(event_text)
            start_raw = fields.get("DTSTART")
            if not start_raw:
                continue
            start = self._parse_ics_value(start_raw)
            end = self._parse_ics_value(fields.get("DTEND", "")) if fields.get("DTEND") else start
            events.append(
                self._event_dict(
                    title=fields.get("SUMMARY", ""),
                    start=start,
                    end=end,
                    location=fields.get("LOCATION") or None,
                    description=fields.get("DESCRIPTION") or None,
                )
            )
        return events

    def _parse_event_fields(self, event_text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for raw_line in event_text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.split(";", 1)[0].upper()] = value.strip()
        return fields

    def _parse_ics_value(self, value: str) -> date | datetime:
        if len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").date()
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        return datetime.strptime(value, "%Y%m%dT%H%M%S")

    def _event_dict(
        self,
        title: str,
        start: date | datetime,
        end: date | datetime,
        location: str | None,
        description: str | None,
    ) -> dict[str, Any]:
        all_day = isinstance(start, date) and not isinstance(start, datetime)
        return {
            "provider": self.name,
            "title": title,
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "location": location,
            "description": description,
            "all_day": all_day,
            "source": "ics",
        }

    def _event_overlaps_day(self, event: dict[str, Any], day: date) -> bool:
        start = self._event_boundary(event["start"])
        end_raw = event.get("end") or event["start"]
        end = self._event_boundary(end_raw)
        if event.get("all_day"):
            end = end if end > start else end + timedelta(days=1)
        elif end <= start:
            end = start + timedelta(minutes=1)

        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day + timedelta(days=1), time.min)
        return start < day_end and end > day_start

    def _event_boundary(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
