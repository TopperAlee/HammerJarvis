from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmailSummary:
    provider: str
    sender: str
    subject: str
    snippet: str
    received_at: str
    is_unread: bool
    has_attachments: bool


@dataclass(frozen=True)
class EmailDraftRequest:
    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class CalendarEventSummary:
    provider: str
    title: str
    start: str
    end: str
    location: str | None
    description: str | None


@dataclass(frozen=True)
class CalendarEventCreateRequest:
    title: str
    start: str
    end: str | None = None
    location: str | None = None
    description: str | None = None
    attendees: list[str] = field(default_factory=list)
