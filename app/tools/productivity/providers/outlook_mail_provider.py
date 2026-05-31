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
            "message": "Outlook Mail ist vorbereitet, aber Microsoft Graph OAuth ist noch nicht verbunden.",
        }

    def create_draft(self, request: EmailDraftRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "confirmation_required": True,
            "draft": request.__dict__,
            "message": (
                "Ich kann den E-Mail-Entwurf vorbereiten. Zum echten Erstellen "
                "oder Senden muss zuerst das Konto verbunden werden."
            ),
        }

    def send_email(self, **_: Any) -> dict[str, Any]:
        return {
            "provider": self.name,
            "blocked": True,
            "message": (
                "Das direkte Senden von E-Mails ist aus Sicherheitsgruenden "
                "blockiert, bis die Bestaetigungslogik und Kontoverbindung "
                "eingerichtet sind."
            ),
        }
