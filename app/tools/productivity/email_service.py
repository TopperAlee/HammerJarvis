from typing import Any

from app.tools.productivity.models import EmailDraftRequest
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.outlook_mail_provider import OutlookMailProvider


class EmailService:
    def __init__(self) -> None:
        self.providers = {
            "gmail": GmailProvider(),
            "outlook_mail": OutlookMailProvider(),
        }

    def search_emails(
        self,
        query: str,
        providers: list[str] | None = None,
    ) -> dict[str, Any]:
        selected = providers or ["gmail", "outlook_mail"]
        return {
            "providers": [
                self.providers[provider].search_emails(query)
                for provider in selected
                if provider in self.providers
            ],
            "message": "E-Mail-Suche ist vorbereitet, aber noch nicht mit echten Konten verbunden.",
        }

    def create_draft(
        self,
        provider: str = "gmail",
        request: EmailDraftRequest | None = None,
    ) -> dict[str, Any]:
        draft = request or EmailDraftRequest(to="", subject="", body="")
        selected = provider if provider in self.providers else "gmail"
        return self.providers[selected].create_draft(draft)

    def send_email(self, provider: str = "gmail", **kwargs: Any) -> dict[str, Any]:
        selected = provider if provider in self.providers else "gmail"
        result = self.providers[selected].send_email(**kwargs)
        return {**result, "blocked": True}
