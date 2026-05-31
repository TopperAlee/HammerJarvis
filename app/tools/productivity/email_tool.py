from typing import Any


class EmailTool:
    def search(self, query: str | None = None) -> dict[str, Any]:
        return {
            "emails": [],
            "query": query,
            "message": "E-Mail-Suche ist vorbereitet, aber noch nicht mit einem echten Konto verbunden.",
        }

    def create_draft(
        self,
        recipient: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return {
            "confirmation_required": True,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "message": "Ich kann E-Mail-Entwuerfe vorbereiten, aber dein echtes E-Mail-Konto ist noch nicht verbunden.",
        }

    def send(self, **_: Any) -> dict[str, Any]:
        return {
            "blocked": True,
            "message": "E-Mails senden ist als RED-Aktion in v0.3 blockiert.",
        }
