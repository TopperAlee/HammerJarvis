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
    assert result["category"] == "account_security"
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
    assert response.json()["category"] == "account_security"


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


def test_openai_data_export_email_is_high_account_security() -> None:
    result = PriorityEngine().classify_email(
        {
            "sender": "OpenAI",
            "subject": "Dein Datenexport wurde gestartet",
            "snippet": "A data export was started for your account.",
        }
    )

    assert result["priority"] == "high"
    assert result["category"] == "account_security"
    assert result["recommended_action"] == "Pruefen, ob du den Datenexport selbst gestartet hast."


def test_openai_data_export_appears_in_important_first() -> None:
    answer = format_daily_briefing(_daily_results_with_emails([
        {
            "sender": "OpenAI",
            "subject": "Dein Datenexport wurde gestartet",
            "snippet": "A data export was started for your account.",
        }
    ]))

    important = answer.split("Posteingang:", 1)[0]
    assert "OpenAI" in important
    assert "OpenAI-Datenexport pruefen." in answer


def test_ecoflow_stale_only_warning_not_in_important_first_when_security_exists() -> None:
    results = _daily_results_with_emails([
        {
            "sender": "OpenAI",
            "subject": "Data export started",
            "snippet": "Export started for your account.",
        }
    ])
    results["ecoflow_energy_overview"] = {
        "human_status": {"overall": "warning", "headline": "EcoFlow laeuft, aber einige Werte sind veraltet.", "details": []},
        "warning_count_by_severity": 2,
        "critical_count": 0,
        "soc_percent": 50,
        "warnings": [{"code": "stale_value", "severity": "warning", "message": "Der Tageswert Solarenergie heute ist veraltet."}],
    }

    answer = format_daily_briefing(results)

    important = answer.split("Posteingang:", 1)[0]
    assert "EcoFlow" not in important
    assert "EcoFlow-Tageswerte bei Gelegenheit pruefen." in answer


def test_ecoflow_low_battery_appears_in_important_first(monkeypatch) -> None:
    monkeypatch.setenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20")
    results = _daily_results_with_emails([])
    results["ecoflow_energy_overview"] = {
        "human_status": {"overall": "warning", "headline": "EcoFlow Batterie niedrig.", "details": ["Batterie: 15 %"]},
        "warning_count_by_severity": 0,
        "critical_count": 0,
        "soc_percent": 15,
        "warnings": [],
    }

    answer = format_daily_briefing(results)

    important = answer.split("Posteingang:", 1)[0]
    assert "EcoFlow-Batterie ist niedrig: 15 %" in important
    assert "EcoFlow-Batterie pruefen." in answer


def test_daily_briefing_does_not_use_generic_short_check_action() -> None:
    answer = format_daily_briefing(_daily_results_with_emails([
        {"sender": "Max Mustermann", "subject": "Hallo", "snippet": ""},
    ]))

    assert "Kurz pruefen" not in answer


def test_voyage_prive_travel_deal_is_low_marketing() -> None:
    result = PriorityEngine().classify_email(
        {
            "sender": '"Laura, Reiseexpertin von Voyage Prive" <news@email.voyageprive.de>',
            "subject": "Roadtrip Hawaii, Neueroeffnung 5* Tuerkei, All-in Barbados -80%, Gardasee ab 56 EUR, Malediven ab 799 EUR",
            "snippet": "Urlaub, Reise und Angebote.",
        }
    )

    assert result["priority"] == "low"
    assert result["category"] == "marketing"
    assert result["category"] != "account_security"
    assert result["confidence"] in {"high", "medium"}


def test_ea_sports_fc_promotion_is_low_marketing() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "EA <news@ea.com>", "subject": "Spiele internationalen Fussball in EA SPORTS FC", "snippet": "Angebot nur heute"}
    )

    assert result["priority"] == "low"
    assert result["category"] == "marketing"


def test_conrad_camping_promotion_is_low_marketing() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "Conrad", "subject": "Camping Angebote und Deals", "snippet": "Rabatt auf Outdoor Produkte"}
    )

    assert result["priority"] == "low"
    assert result["category"] == "marketing"


def test_wonda_suggestions_are_low_info() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "Wonda", "subject": "Neue Vorschlaege fuer dich", "snippet": "Suggestions and updates"}
    )

    assert result["priority"] == "low"
    assert result["category"] == "info"


def test_news_sender_with_discount_symbols_is_not_high() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "news@email.voyageprive.de", "subject": "Malediven -80% ab 799 EUR", "snippet": ""}
    )

    assert result["priority"] != "high"
    assert result["category"] == "marketing"


def test_unknown_noreply_news_sender_defaults_to_info() -> None:
    result = PriorityEngine().classify_email(
        {"sender": "noreply@unknown.example", "subject": "Produkt Update", "snippet": "Neue Vorschlaege"}
    )

    assert result["priority"] == "info"
    assert result["category"] == "unknown"


def test_daily_briefing_excludes_marketing_from_important_first_precision() -> None:
    answer = format_daily_briefing(_daily_results_with_emails([
        {
            "sender": "news@email.voyageprive.de",
            "subject": "Roadtrip Hawaii, Malediven -80%",
            "snippet": "Reise Angebot",
        },
        {"sender": "EA <news@ea.com>", "subject": "Spiele internationalen Fussball", "snippet": ""},
    ]))

    important = answer.split("Posteingang:", 1)[0]
    assert "Voyage" not in important
    assert "EA" not in important
    assert "Keine wirklich wichtigen neuen E-Mails erkannt." in answer
    assert "Kontoaktion" not in answer


def _daily_results_with_emails(emails: list[dict]) -> dict:
    return {
        "gmail_unread_recent": {
            "providers": [{"provider": "gmail", "connected": True, "emails": emails}],
            "total_email_count": len(emails),
            "unread_count": len(emails),
        },
        "home_assistant_get_problems": {
            "critical_count": 0,
            "warning_count": 0,
            "informational_count": 0,
            "critical": [],
            "warning": [],
            "informational": [],
        },
        "timetree_today": {"events": []},
        "ecoflow_energy_overview": {
            "human_status": {"overall": "ok", "headline": "EcoFlow laeuft.", "details": []},
            "warnings": [],
            "critical_count": 0,
            "warning_count_by_severity": 0,
            "soc_percent": 80,
        },
    }
