from typing import Any

from app.tools.productivity.models import EmailDraftRequest


class OutlookMailProvider:
    name = "outlook_mail"

    def search_emails(self, query: str) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "emails": [],
            "query": query,
            "message": "Microsoft Graph OAuth fuer Outlook Mail ist noch nicht verbunden.",
        }

    def create_draft(self, request: EmailDraftRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "confirmation_required": True,
            "draft": request.__dict__,
            "message": "Microsoft Graph OAuth fuer Outlook Mail ist noch nicht verbunden. Es wurde kein echter Entwurf erstellt.",
        }

    def send_email(self, **_: Any) -> dict[str, Any]:
        return {
            "provider": self.name,
            "blocked": True,
            "message": "Outlook-Mail-Versand ist in dieser Version blockiert.",
        }
