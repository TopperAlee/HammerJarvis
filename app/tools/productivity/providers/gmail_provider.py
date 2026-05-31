import os
from pathlib import Path
from typing import Any

from app.tools.productivity.models import EmailDraftRequest


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_NOT_CONNECTED_MESSAGE = (
    "Gmail ist vorbereitet, aber noch nicht verbunden. Lege "
    "gmail_credentials.json ab und setze GMAIL_ENABLED=true."
)


class GmailProvider:
    name = "gmail"

    def search_emails(self, query: str) -> dict[str, Any]:
        if not self._is_configured():
            return self._mock_search_response(query)

        service = self._build_service()
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=10)
            .execute()
        )
        messages = response.get("messages", [])
        emails = [
            self.get_message_summary(str(message["id"]), service=service)
            for message in messages
            if message.get("id")
        ]
        return {
            "provider": self.name,
            "connected": True,
            "emails": emails,
            "query": query,
            "message": (
                "Keine passenden Gmail-Nachrichten gefunden."
                if not emails
                else f"{len(emails)} Gmail-Nachrichten gefunden."
            ),
        }

    def get_message_summary(
        self,
        message_id: str,
        service: Any | None = None,
    ) -> dict[str, Any]:
        gmail_service = service or self._build_service()
        message = (
            gmail_service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        payload = message.get("payload", {})
        headers = {
            header.get("name", "").lower(): header.get("value", "")
            for header in payload.get("headers", [])
        }
        labels = set(message.get("labelIds", []))
        return {
            "provider": self.name,
            "id": message_id,
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "snippet": message.get("snippet", ""),
            "is_unread": "UNREAD" in labels,
            "has_attachments": self._has_attachments(payload),
        }

    def create_draft(self, request: EmailDraftRequest) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": self.status()["connected"],
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

    def status(self) -> dict[str, Any]:
        credentials_file = self._credentials_file()
        token_file = self._token_file()
        enabled = self._enabled()
        credentials_file_exists = credentials_file.is_file()
        token_file_exists = token_file.is_file()
        return {
            "provider": self.name,
            "enabled": enabled,
            "credentials_file_exists": credentials_file_exists,
            "token_file_exists": token_file_exists,
            "connected": enabled and credentials_file_exists and token_file_exists,
        }

    def _is_configured(self) -> bool:
        return self._enabled() and self._credentials_file().is_file()

    def _get_credentials(self) -> Any:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_file = self._token_file()
        credentials = None
        if token_file.is_file():
            credentials = Credentials.from_authorized_user_file(
                str(token_file),
                [GMAIL_READONLY_SCOPE],
            )

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._credentials_file()),
                [GMAIL_READONLY_SCOPE],
            )
            credentials = flow.run_local_server(port=0)

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    def _build_service(self) -> Any:
        from googleapiclient.discovery import build

        return build("gmail", "v1", credentials=self._get_credentials())

    def _mock_search_response(self, query: str) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": False,
            "emails": [],
            "query": query,
            "message": GMAIL_NOT_CONNECTED_MESSAGE,
        }

    def _enabled(self) -> bool:
        return os.getenv("GMAIL_ENABLED", "false").strip().lower() == "true"

    def _credentials_file(self) -> Path:
        return Path(
            os.getenv(
                "GOOGLE_GMAIL_CREDENTIALS_FILE",
                "app/secrets/google/gmail_credentials.json",
            )
        )

    def _token_file(self) -> Path:
        return Path(
            os.getenv(
                "GOOGLE_GMAIL_TOKEN_FILE",
                "app/secrets/google/gmail_token.json",
            )
        )

    def _has_attachments(self, payload: dict[str, Any]) -> bool:
        parts = payload.get("parts", [])
        for part in parts:
            body = part.get("body", {})
            filename = str(part.get("filename", ""))
            if filename or body.get("attachmentId"):
                return True
            if self._has_attachments(part):
                return True
        return False
