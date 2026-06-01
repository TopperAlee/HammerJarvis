import html
import re
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
        provider_results = [
            self._search_provider(provider, query)
            for provider in selected
            if provider in self.providers
        ]
        summary = _build_email_summary(provider_results)
        return {
            "providers": provider_results,
            **summary,
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

    def _search_provider(self, provider: str, query: str) -> dict[str, Any]:
        try:
            return self.providers[provider].search_emails(query)
        except Exception:
            if provider == "gmail":
                gmail_provider = self.providers["gmail"]
                if hasattr(gmail_provider, "error_response"):
                    return gmail_provider.error_response(query)
            return {
                "provider": provider,
                "connected": False,
                "error": True,
                "message": "Provider konnte nicht durchsucht werden.",
                "emails": [],
            }


def clean_email_snippet(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= 180:
        return cleaned
    return cleaned[:177].rstrip() + "..."


def _build_email_summary(provider_results: list[dict[str, Any]]) -> dict[str, Any]:
    connected_providers = [
        str(result["provider"])
        for result in provider_results
        if result.get("connected") is True
    ]
    disconnected_providers = [
        str(result["provider"])
        for result in provider_results
        if result.get("connected") is not True
    ]
    total_email_count = sum(
        len(result.get("emails", []))
        for result in provider_results
        if result.get("connected") is True
    )
    unread_values = [
        email.get("is_unread")
        for result in provider_results
        for email in result.get("emails", [])
        if result.get("connected") is True and "is_unread" in email
    ]
    unread_count = sum(1 for value in unread_values if value is True)

    return {
        "total_email_count": total_email_count,
        "connected_providers": connected_providers,
        "disconnected_providers": disconnected_providers,
        "unread_count": unread_count if unread_values else None,
        "message": _build_email_message(provider_results, total_email_count),
    }


def _build_email_message(
    provider_results: list[dict[str, Any]],
    total_email_count: int,
) -> str:
    if _provider_has_error(provider_results, "gmail"):
        return (
            "Gmail ist noch nicht korrekt verbunden. Outlook Mail ist weiterhin "
            "vorbereitet, aber noch nicht verbunden."
        )

    connected_results = [
        result for result in provider_results if result.get("connected") is True
    ]
    if not connected_results:
        return (
            "Ich kann Gmail und Outlook grundsaetzlich durchsuchen, aber "
            "die Konten sind noch nicht verbunden. Die E-Mail-Schnittstellen "
            "sind vorbereitet."
        )

    provider_parts = [
        f"{len(result.get('emails', []))} {_display_provider_name(str(result.get('provider')))}-Nachrichten"
        for result in connected_results
    ]
    disconnected_parts = [
        f"{_display_provider_name(str(result.get('provider')))} ist noch nicht verbunden"
        for result in provider_results
        if result.get("connected") is not True and not result.get("error")
    ]

    if len(connected_results) == 1 and connected_results[0].get("provider") == "gmail":
        if total_email_count:
            message = f"Ich habe {total_email_count} Gmail-Nachrichten gefunden."
        else:
            message = "Ich habe in Gmail keine passenden Nachrichten gefunden."
    else:
        message = "Ich habe " + ", ".join(provider_parts) + " gefunden."

    if disconnected_parts:
        message += " " + " ".join(f"{part}." for part in disconnected_parts)
    return message


def _provider_has_error(provider_results: list[dict[str, Any]], provider: str) -> bool:
    return any(
        result.get("provider") == provider and result.get("error") is True
        for result in provider_results
    )


def _display_provider_name(provider: str) -> str:
    return {
        "gmail": "Gmail",
        "outlook_mail": "Outlook Mail",
    }.get(provider, provider)
