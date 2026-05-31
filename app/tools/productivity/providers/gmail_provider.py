from typing import Any

from app.tools.productivity.models import EmailDraftRequest


class GmailProvider:
    name = "gmail"

    def search_emails(self, query: str) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "emails": [],
            "query": query,
            "message": "Gmail OAuth ist noch nicht verbunden.",
        }

    def create_draft(self, request: EmailDraftRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "confirmation_required": True,
            "draft": request.__dict__,
            "message": "Gmail OAuth ist noch nicht verbunden. Es wurde keine echte E-Mail erstellt.",
        }

    def send_email(self, **_: Any) -> dict[str, Any]:
        return {
            "provider": self.name,
            "blocked": True,
            "message": "Gmail-Versand ist in dieser Version blockiert.",
        }
