from app.assistant.llm_client import LLMClient
from app.main import app
from fastapi.testclient import TestClient
import pytest
from datetime import date, timedelta


client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_real_gmail(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv(
        "GOOGLE_GMAIL_CREDENTIALS_FILE",
        str(tmp_path / "gmail_credentials.json"),
    )
    monkeypatch.setenv("GOOGLE_GMAIL_TOKEN_FILE", str(tmp_path / "gmail_token.json"))
    monkeypatch.setenv("TIMETREE_ENABLED", "false")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(tmp_path / "timetree.ics"))
    monkeypatch.setenv("LLM_ENABLED", "false")


def test_assistant_chat_returns_200() -> None:
    response = client.post("/assistant/chat", json={"message": "Hallo Jarvis"})

    assert response.status_code == 200
    assert response.json()["mode"] in {"rule_based", "rule_based_fallback"}


def test_assistant_ecoflow_command_routes_to_ecoflow_tool(monkeypatch) -> None:
    overview = {
        "human_status": {
            "headline": "EcoFlow laeuft.",
            "details": ["Batterie: 80 %"],
        },
        "warnings": [],
    }

    def fake_overview(self):
        return overview

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_ecoflow_energy_overview",
        fake_overview,
    )

    response = client.post("/assistant/chat", json={"message": "EcoFlow Energie"})

    assert response.status_code == 200
    assert response.json()["tool"] == "ecoflow_energy_overview"
    assert response.json()["answer"] == "EcoFlow laeuft.\n- Batterie: 80 %"


def test_assistant_calendar_today_routes_to_mock() -> None:
    response = client.post(
        "/assistant/chat", json={"message": "Welche Termine habe ich heute?"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "calendar_today"
    assert "Kalender" in response.json()["answer"]


def test_assistant_calendar_today_routes_for_was_steht_heute() -> None:
    response = client.post(
        "/assistant/chat", json={"message": "Was steht heute im Kalender?"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "calendar_today"


def test_assistant_email_search_routes_to_mock() -> None:
    response = client.post(
        "/assistant/chat", json={"message": "Suche E-Mails von Max"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "email_search_all"
    assert "E-Mail" in response.json()["answer"]


def test_assistant_email_search_routes_for_new_emails() -> None:
    response = client.post(
        "/assistant/chat", json={"message": "Habe ich neue E-Mails?"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "email_search_all"


def test_assistant_email_create_draft_requires_confirmation() -> None:
    response = client.post(
        "/assistant/chat", json={"message": "Schreibe eine E-Mail an Max"}
    )

    assert response.status_code == 200
    assert response.json()["confirmation_required"] is True
    assert response.json()["risk"] == "YELLOW"
    assert response.json()["tool"] == "email_create_draft"


def test_assistant_email_send_is_blocked() -> None:
    response = client.post("/assistant/chat", json={"message": "Sende eine E-Mail"})

    assert response.status_code == 200
    assert response.json()["blocked"] is True
    assert response.json()["risk"] == "RED"
    assert response.json()["tool"] == "email_send_blocked"


def test_assistant_providers_endpoint_returns_all_providers() -> None:
    response = client.get("/assistant/providers")

    assert response.status_code == 200
    assert response.json()["email"] == ["gmail", "outlook_mail"]
    assert response.json()["calendar"] == [
        "outlook_calendar",
        "google_calendar",
        "timetree",
    ]
    assert response.json()["connected"]["timetree"] == "limited"


def test_calendar_today_endpoint_returns_outlook_mock_status() -> None:
    response = client.get("/assistant/calendar/today")

    assert response.status_code == 200
    assert response.json()["providers"][0]["provider"] == "outlook_calendar"
    assert "Microsoft Graph" in response.json()["providers"][0]["message"]


def test_email_search_endpoint_returns_gmail_and_outlook_mock_results() -> None:
    response = client.get("/assistant/email/search", params={"q": "Max"})

    assert response.status_code == 200
    providers = [item["provider"] for item in response.json()["providers"]]
    assert providers == ["gmail", "outlook_mail"]


def test_gmail_status_returns_disabled_when_env_false(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.gmail_provider import GmailProvider

    credentials_file = tmp_path / "gmail_credentials.json"
    token_file = tmp_path / "gmail_token.json"
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv("GOOGLE_GMAIL_CREDENTIALS_FILE", str(credentials_file))
    monkeypatch.setenv("GOOGLE_GMAIL_TOKEN_FILE", str(token_file))

    status = GmailProvider().status()

    assert status == {
        "provider": "gmail",
        "enabled": False,
        "credentials_file_exists": False,
        "token_file_exists": False,
        "connected": False,
    }


def test_gmail_provider_returns_mock_when_not_configured(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.gmail_provider import GmailProvider

    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv(
        "GOOGLE_GMAIL_CREDENTIALS_FILE", str(tmp_path / "gmail_credentials.json")
    )

    result = GmailProvider().search_emails("Max")

    assert result["provider"] == "gmail"
    assert result["connected"] is False
    assert result["emails"] == []
    assert "noch nicht verbunden" in result["message"]


def test_gmail_status_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv(
        "GOOGLE_GMAIL_CREDENTIALS_FILE", str(tmp_path / "gmail_credentials.json")
    )
    monkeypatch.setenv("GOOGLE_GMAIL_TOKEN_FILE", str(tmp_path / "gmail_token.json"))

    response = client.get("/assistant/gmail/status")

    assert response.status_code == 200
    assert response.json()["provider"] == "gmail"
    assert response.json()["enabled"] is False


def test_gmail_invalid_client_error_returns_structured_error(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.gmail_provider import GmailProvider

    class InvalidClientError(Exception):
        pass

    credentials_file = tmp_path / "gmail_credentials.json"
    credentials_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GMAIL_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_GMAIL_CREDENTIALS_FILE", str(credentials_file))

    def fail_build_service(self):
        raise InvalidClientError(
            "invalid_client: client_secret=do-not-leak authorization_url=do-not-leak"
        )

    monkeypatch.setattr(GmailProvider, "_build_service", fail_build_service)

    result = GmailProvider().search_emails("Max")

    assert result["provider"] == "gmail"
    assert result["connected"] is False
    assert result["error"] is True
    assert result["emails"] == []
    assert "Gmail konnte nicht verbunden" in result["message"]
    assert "Client Secret" in result["technical_hint"]
    assert "do-not-leak" not in str(result)


def test_email_service_keeps_outlook_when_gmail_fails(monkeypatch) -> None:
    from app.tools.productivity.email_service import EmailService

    def fail_gmail(self, query):
        raise RuntimeError("secret failure")

    monkeypatch.setattr(
        "app.tools.productivity.providers.gmail_provider.GmailProvider.search_emails",
        fail_gmail,
    )

    result = EmailService().search_emails("Max")

    assert [item["provider"] for item in result["providers"]] == [
        "gmail",
        "outlook_mail",
    ]
    assert result["providers"][0]["error"] is True
    assert result["providers"][1]["provider"] == "outlook_mail"


def test_email_search_endpoint_returns_200_when_gmail_fails(monkeypatch) -> None:
    def fail_gmail(self, query):
        raise RuntimeError("secret failure")

    monkeypatch.setattr(
        "app.tools.productivity.providers.gmail_provider.GmailProvider.search_emails",
        fail_gmail,
    )

    response = client.get("/assistant/email/search", params={"q": "Max"})

    assert response.status_code == 200
    assert response.json()["providers"][0]["provider"] == "gmail"
    assert response.json()["providers"][0]["error"] is True
    assert response.json()["providers"][1]["provider"] == "outlook_mail"


def test_assistant_chat_returns_german_answer_when_gmail_fails(monkeypatch) -> None:
    def fail_gmail(self, query):
        raise RuntimeError("secret failure")

    monkeypatch.setattr(
        "app.tools.productivity.providers.gmail_provider.GmailProvider.search_emails",
        fail_gmail,
    )

    response = client.post(
        "/assistant/chat", json={"message": "Habe ich neue E-Mails?"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "email_search_all"
    assert "Gmail ist noch nicht korrekt verbunden" in response.json()["answer"]
    assert "v0.1" not in response.json()["answer"]


def test_email_service_summarizes_connected_gmail_with_outlook_disconnected(monkeypatch) -> None:
    from app.tools.productivity.email_service import EmailService

    emails = [
        {
            "sender": f"Sender {index}",
            "subject": f"Subject {index}",
            "date": "Mon, 01 Jun 2026 10:00:00 +0000",
            "snippet": "Text",
            "is_unread": True,
        }
        for index in range(6)
    ]

    def gmail_results(self, query):
        return {
            "provider": "gmail",
            "connected": True,
            "emails": emails,
            "query": query,
            "message": "6 Gmail-Nachrichten gefunden.",
        }

    monkeypatch.setattr(
        "app.tools.productivity.providers.gmail_provider.GmailProvider.search_emails",
        gmail_results,
    )

    result = EmailService().search_emails("is:unread newer_than:30d")

    assert result["total_email_count"] == 6
    assert result["unread_count"] == 6
    assert result["connected_providers"] == ["gmail"]
    assert result["disconnected_providers"] == ["outlook_mail"]
    assert result["message"] == (
        "Ich habe 6 Gmail-Nachrichten gefunden. Outlook Mail ist noch nicht verbunden."
    )


def test_assistant_email_answer_includes_count_and_limits_to_five(monkeypatch) -> None:
    emails = [
        {
            "sender": f"Sender {index}",
            "subject": f"Subject {index}",
            "date": f"2026-06-0{index}",
            "snippet": "Text",
            "is_unread": True,
        }
        for index in range(1, 7)
    ]

    def gmail_results(self, query):
        return {
            "provider": "gmail",
            "connected": True,
            "emails": emails,
            "query": query,
            "message": "6 Gmail-Nachrichten gefunden.",
        }

    monkeypatch.setattr(
        "app.tools.productivity.providers.gmail_provider.GmailProvider.search_emails",
        gmail_results,
    )

    response = client.post(
        "/assistant/chat", json={"message": "Habe ich neue E-Mails?"}
    )

    answer = response.json()["answer"]
    assert "Ich habe 6 Gmail-Nachrichten gefunden" in answer
    assert "1. Sender 1: Subject 1" in answer
    assert "5. Sender 5: Subject 5" in answer
    assert "6. Sender 6" not in answer


def test_clean_email_snippet_removes_invisible_characters_and_html_entities() -> None:
    from app.tools.productivity.email_service import clean_email_snippet

    dirty = "\u200b\u200cHello&nbsp;&nbsp;World&#39;s\n\n" + ("x" * 300)
    cleaned = clean_email_snippet(dirty)

    assert "\u200b" not in cleaned
    assert "\u200c" not in cleaned
    assert "World's" in cleaned
    assert "  " not in cleaned
    assert len(cleaned) <= 180


def test_assistant_email_search_routes_unread_to_gmail_query(monkeypatch) -> None:
    captured = {}

    def fake_search(self, query, providers=None):
        captured["query"] = query
        return {"providers": [], "message": "ok"}

    monkeypatch.setattr(
        "app.tools.productivity.email_service.EmailService.search_emails",
        fake_search,
    )

    response = client.post(
        "/assistant/chat", json={"message": "Zeig mir ungelesene E-Mails"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "email_search_all"
    assert captured["query"] == "is:unread newer_than:30d"


def test_assistant_email_search_routes_sender_to_gmail_query(monkeypatch) -> None:
    captured = {}

    def fake_search(self, query, providers=None):
        captured["query"] = query
        return {"providers": [], "message": "ok"}

    monkeypatch.setattr(
        "app.tools.productivity.email_service.EmailService.search_emails",
        fake_search,
    )

    response = client.post(
        "/assistant/chat", json={"message": "Suche E-Mails von Max"}
    )

    assert response.status_code == 200
    assert response.json()["tool"] == "email_search_all"
    assert captured["query"] == "from:Max newer_than:90d"


def test_timetree_status_endpoint_returns_limited() -> None:
    response = client.get("/assistant/timetree/status")

    assert response.status_code == 200
    assert response.json()["provider"] == "timetree"
    assert response.json()["connected"] == "limited"


def test_timetree_create_event_is_blocked() -> None:
    from app.tools.productivity.models import CalendarEventCreateRequest
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    result = TimeTreeProvider().create_event(
        CalendarEventCreateRequest(title="Test", start="2026-06-01T10:00:00")
    )

    assert result["blocked"] is True
    assert result["status"] == "not_supported"


def test_timetree_status_disabled(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    monkeypatch.setenv("TIMETREE_ENABLED", "false")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(tmp_path / "missing.ics"))

    result = TimeTreeProvider().status()

    assert result["provider"] == "timetree"
    assert result["enabled"] is False
    assert result["connected"] == "limited"
    assert "deaktiviert" in result["message"]


def test_timetree_enabled_missing_ics_returns_clear_message(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(tmp_path / "missing.ics"))

    result = TimeTreeProvider().list_events()

    assert result["enabled"] is True
    assert result["connected"] is False
    assert result["events"] == []
    assert result["message"] == "TimeTree ICS-Datei wurde nicht gefunden."


def test_timetree_valid_ics_with_today_event_returns_event(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    ics_file = tmp_path / "timetree.ics"
    today = date.today()
    ics_file.write_text(
        _ics(
            f"""
BEGIN:VEVENT
UID:today@example
SUMMARY:Werkstatt
DTSTART:{today.strftime('%Y%m%d')}T090000
DTEND:{today.strftime('%Y%m%d')}T100000
LOCATION:Halle
DESCRIPTION:Planung
END:VEVENT
"""
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(ics_file))

    result = TimeTreeProvider().list_today_events()

    assert result["count"] == 1
    assert result["events"][0]["title"] == "Werkstatt"
    assert result["events"][0]["all_day"] is False
    assert result["events"][0]["source"] == "ics"


def test_timetree_valid_ics_with_all_day_today_event_returns_event(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    ics_file = tmp_path / "timetree.ics"
    today = date.today()
    tomorrow = today + timedelta(days=1)
    ics_file.write_text(
        _ics(
            f"""
BEGIN:VEVENT
UID:allday@example
SUMMARY:Ganztag
DTSTART;VALUE=DATE:{today.strftime('%Y%m%d')}
DTEND;VALUE=DATE:{tomorrow.strftime('%Y%m%d')}
END:VEVENT
"""
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(ics_file))

    result = TimeTreeProvider().list_today_events()

    assert result["count"] == 1
    assert result["events"][0]["title"] == "Ganztag"
    assert result["events"][0]["all_day"] is True


def test_timetree_future_event_not_in_today(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    ics_file = tmp_path / "timetree.ics"
    future = date.today() + timedelta(days=7)
    ics_file.write_text(
        _ics(
            f"""
BEGIN:VEVENT
UID:future@example
SUMMARY:Zukunft
DTSTART:{future.strftime('%Y%m%d')}T090000
DTEND:{future.strftime('%Y%m%d')}T100000
END:VEVENT
"""
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(ics_file))

    result = TimeTreeProvider().list_today_events()

    assert result["count"] == 0
    assert result["events"] == []


def test_timetree_invalid_ics_does_not_crash(monkeypatch, tmp_path) -> None:
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    ics_file = tmp_path / "timetree.ics"
    ics_file.write_text("not an ics file", encoding="utf-8")
    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(ics_file))

    result = TimeTreeProvider().list_events()

    assert result["provider"] == "timetree"
    assert result["error"] is True
    assert result["events"] == []


def test_timetree_today_endpoint_returns_200() -> None:
    response = client.get("/assistant/timetree/today")

    assert response.status_code == 200
    assert response.json()["provider"] == "timetree"


def test_timetree_events_endpoint_returns_200() -> None:
    response = client.get("/assistant/timetree/events")

    assert response.status_code == 200
    assert response.json()["provider"] == "timetree"


def test_assistant_timetree_today_intent_routes_to_today(monkeypatch, tmp_path) -> None:
    ics_file = tmp_path / "timetree.ics"
    today = date.today()
    ics_file.write_text(
        _ics(
            f"""
BEGIN:VEVENT
UID:voice@example
SUMMARY:Voice Termin
DTSTART:{today.strftime('%Y%m%d')}T130000
DTEND:{today.strftime('%Y%m%d')}T140000
END:VEVENT
"""
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIMETREE_ENABLED", "true")
    monkeypatch.setenv("TIMETREE_ICS_FILE", str(ics_file))

    response = client.post("/assistant/chat", json={"message": "TimeTree heute"})

    assert response.status_code == 200
    assert response.json()["tool"] == "timetree_today"
    assert "Heute stehen 1 TimeTree-Termine an" in response.json()["answer"]
    assert "Voice Termin" in response.json()["answer"]


def test_email_service_send_email_is_blocked() -> None:
    from app.tools.productivity.email_service import EmailService

    result = EmailService().send_email("gmail")

    assert result["blocked"] is True


def test_missing_openai_api_key_does_not_crash(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client_without_key = LLMClient()

    result = client_without_key.generate_response("Was kannst du?")

    assert client_without_key.is_available() is False
    assert client_without_key.mode() == "rule_based_fallback"
    assert result["available"] is False


def test_existing_chat_still_works() -> None:
    response = client.post("/chat", json={"message": "Was kannst du heute tun?"})

    assert response.status_code == 200
    assert response.json()["intent"] == "fallback"


def test_existing_dashboard_still_works() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200


def test_assistant_timetree_intent_routes_to_status() -> None:
    response = client.post("/assistant/chat", json={"message": "Was ist mit TimeTree?"})

    assert response.status_code == 200
    assert response.json()["tool"] == "timetree_today"


def _ics(body: str) -> str:
    return "BEGIN:VCALENDAR\nVERSION:2.0\n" + body.strip() + "\nEND:VCALENDAR\n"
