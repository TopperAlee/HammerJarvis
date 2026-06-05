from fastapi.testclient import TestClient

from app.assistant.formatters.mission_formatter import format_daily_briefing
from app.assistant.priority_engine import PriorityEngine
from app.main import app
from app.tools.home_assistant import HomeAssistantTool


client = TestClient(app)


def test_github_oauth_email_is_high_security() -> None:
    result = PriorityEngine().classify_email(
        {
            "sender": "GitHub",
            "subject": "A third-party OAuth application has been added",
            "snippet": "A new OAuth application was authorized.",
        }
    )

    assert result["priority"] == "high"
    assert result["category"] == "security"
    assert "OAuth-App" in result["recommended_action"]


def test_fernakademie_platform_email_is_high_academy() -> None:
    result = PriorityEngine().classify_email(
        {
            "sender": "Fernakademie",
            "subject": "Neue Nachricht auf der Online-Plattform",
            "snippet": "Bitte pruefe deine Lernplattform.",
        }
    )

    assert result["priority"] == "high"
    assert result["category"] == "academy"


def test_ollama_welcome_email_is_info() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "Ollama", "subject": "Thank you for joining Ollama", "snippet": ""}
    )

    assert result["priority"] == "info"
    assert result["category"] == "info"


def test_linkedin_job_alert_is_medium_job() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "LinkedIn", "subject": "Job alert: neue Stellenangebote", "snippet": ""}
    )

    assert result["priority"] == "medium"
    assert result["category"] == "job"


def test_campact_newsletter_is_low_newsletter() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "Campact", "subject": "Newsletter: neue Kampagne", "snippet": ""}
    )

    assert result["priority"] == "low"
    assert result["category"] == "newsletter"


def test_hot_stock_email_is_suspicious() -> None:
    result = PriorityEngine().classify_email(
        {
            "sender": "Boersenbrief",
            "subject": "Hot-Stock: 500% Gewinn schnell sein",
            "snippet": "Depotwert vor Neu-Kauf.",
        }
    )

    assert result["category"] == "spam"
    assert result["priority"] in {"low", "info"}


def test_ignored_home_assistant_entity_is_not_counted_critical(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
                "state": "unavailable",
            }
        ],
    )

    result = tool.get_problem_entities()

    assert result["critical_count"] == 0
    assert result["informational_count"] == 1
    assert result["informational"][0]["entity_id"] == "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro"


def test_daily_briefing_priorities_include_only_high_and_critical_items() -> None:
    answer = format_daily_briefing(
        {
            "gmail_unread_recent": {
                "providers": [
                    {
                        "provider": "gmail",
                        "connected": True,
                        "emails": [
                            {
                                "sender": "GitHub",
                                "subject": "A third-party OAuth application has been added",
                                "snippet": "",
                            },
                            {"sender": "Campact", "subject": "Newsletter", "snippet": ""},
                        ],
                    }
                ],
                "total_email_count": 2,
                "unread_count": 2,
            },
            "home_assistant_get_problems": {
                "critical_count": 0,
                "warning_count": 0,
                "informational_count": 1,
                "critical": [],
                "warning": [],
                "informational": [
                    {
                        "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
                        "state": "unavailable",
                        "message": "Bekannte optionale Entity ignoriert.",
                    }
                ],
            },
            "timetree_today": {"events": []},
            "ecoflow_energy_overview": {
                "human_status": {"headline": "EcoFlow laeuft.", "details": ["Batterie: 35 %"]},
                "warnings": [],
            },
        }
    )

    important = answer.split("Posteingang:", 1)[0]
    assert "GitHub" in important
    assert "Campact" not in important
    assert "1 kritische Home-Assistant-Probleme" not in answer
    assert "Keine echten kritischen Home-Assistant-Probleme" in answer


def test_priority_rules_endpoint_returns_200() -> None:
    response = client.get("/assistant/priority/rules")

    assert response.status_code == 200
    assert "email_high_keywords" in response.json()


def test_email_score_endpoint_returns_classification() -> None:
    response = client.post(
        "/assistant/priority/email-score",
        json={
            "sender": "GitHub",
            "subject": "OAuth application authorized",
            "snippet": "",
        },
    )

    assert response.status_code == 200
    assert response.json()["priority"] == "high"
    assert response.json()["category"] == "security"


def test_lotto24_is_low_marketing_from_personal_rule() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "LOTTO24", "subject": "Jackpot wartet", "snippet": ""}
    )

    assert result["priority"] == "low"
    assert result["category"] == "marketing"
    assert result["source"] == "personal_rule"


def test_dreame_is_low_marketing_from_personal_rule() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "Dreame", "subject": "Jetzt erhaeltlich", "snippet": "Produktwerbung"}
    )

    assert result["priority"] == "low"
    assert result["category"] == "marketing"
    assert result["source"] == "personal_rule"


def test_unknown_automated_sender_is_not_high_by_default() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "noreply@example.com", "subject": "Status Update", "snippet": ""}
    )

    assert result["priority"] != "high"


def test_daily_briefing_excludes_low_marketing_from_important_first() -> None:
    answer = format_daily_briefing(
        {
            "gmail_unread_recent": {
                "providers": [
                    {
                        "provider": "gmail",
                        "connected": True,
                        "emails": [
                            {
                                "sender": "Fernakademie",
                                "subject": "Neue Nachricht auf der Online-Plattform",
                                "snippet": "",
                            },
                            {
                                "sender": "GitHub",
                                "subject": "OAuth application authorized",
                                "snippet": "",
                            },
                            {"sender": "LOTTO24", "subject": "Jackpot", "snippet": ""},
                            {"sender": "Dreame", "subject": "Jetzt erhaeltlich", "snippet": ""},
                        ],
                    }
                ],
                "total_email_count": 4,
                "unread_count": 4,
            },
            "home_assistant_get_problems": {"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
            "timetree_today": {"events": []},
            "ecoflow_energy_overview": {"human_status": {"headline": "EcoFlow laeuft.", "details": []}, "warnings": []},
        }
    )

    important = answer.split("Posteingang:", 1)[0]
    assert "Fernakademie" in important
    assert "GitHub" in important
    assert "LOTTO24" not in important
    assert "Dreame" not in important
    assert "Info / Niedrige Prioritaet:" in answer


def test_feedback_command_lotto24_unimportant_adds_low_sender_rule(monkeypatch, tmp_path) -> None:
    rules_file = tmp_path / "personal_priority_rules.json"
    monkeypatch.setenv("PERSONAL_PRIORITY_RULES_FILE", str(rules_file))

    response = client.post("/assistant/chat", json={"message": "Jarvis, LOTTO24 ist unwichtig."})

    assert response.status_code == 200
    assert "LOTTO24" in response.json()["answer"]
    rules = client.get("/assistant/priority/personal-rules").json()
    assert any(item["match"] == "lotto24" and item["priority"] == "low" for item in rules["sender_rules"])


def test_feedback_command_fernakademie_important_adds_high_sender_rule(monkeypatch, tmp_path) -> None:
    rules_file = tmp_path / "personal_priority_rules.json"
    monkeypatch.setenv("PERSONAL_PRIORITY_RULES_FILE", str(rules_file))

    response = client.post("/assistant/chat", json={"message": "Jarvis, Fernakademie ist wichtig."})

    assert response.status_code == 200
    rules = client.get("/assistant/priority/personal-rules").json()
    assert any(item["match"] == "fernakademie" and item["priority"] == "high" for item in rules["sender_rules"])


def test_personal_rules_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PERSONAL_PRIORITY_RULES_FILE", str(tmp_path / "rules.json"))

    response = client.get("/assistant/priority/personal-rules")

    assert response.status_code == 200
    assert "sender_rules" in response.json()


def test_post_sender_rule_works(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PERSONAL_PRIORITY_RULES_FILE", str(tmp_path / "rules.json"))

    response = client.post(
        "/assistant/priority/personal-rules/sender",
        json={"match": "example", "priority": "low", "category": "marketing", "reason": "Test"},
    )

    assert response.status_code == 200
    assert any(item["match"] == "example" for item in response.json()["sender_rules"])


def test_delete_personal_rule_works(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PERSONAL_PRIORITY_RULES_FILE", str(tmp_path / "rules.json"))
    client.post(
        "/assistant/priority/personal-rules/sender",
        json={"match": "lotto24", "priority": "low", "category": "marketing", "reason": "Test"},
    )

    response = client.request("DELETE", "/assistant/priority/personal-rules", json={"match": "lotto24"})

    assert response.status_code == 200
    assert not any(item["match"] == "lotto24" for item in response.json()["sender_rules"])
