from app.assistant.llm_client import LLMClient
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


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
    assert response.json()["status"] == "limited"


def test_timetree_create_event_is_blocked() -> None:
    from app.tools.productivity.models import CalendarEventCreateRequest
    from app.tools.productivity.providers.timetree_provider import TimeTreeProvider

    result = TimeTreeProvider().create_event(
        CalendarEventCreateRequest(title="Test", start="2026-06-01T10:00:00")
    )

    assert result["blocked"] is True
    assert result["status"] == "limited"


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
    assert response.json()["tool"] == "timetree_status"
    assert response.json()["result"]["status"] == "limited"
