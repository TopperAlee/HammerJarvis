from typing import Any

from fastapi.testclient import TestClient

from app.agent.permissions import ActionRisk
from app.assistant.tool_registry import ToolRegistry
from app.assistant.watchers import WatcherController
from app.main import app


client = TestClient(app)


def test_ecoflow_soc_18_creates_high_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path, {"ecoflow_energy_overview": _ecoflow(18)})

    result = controller.run_once()

    assert result["created_count"] == 1
    assert result["alerts"][0]["rule_id"] == "ecoflow_low_battery"
    assert result["alerts"][0]["severity"] == "high"
    assert "18" in result["alerts"][0]["message"]


def test_ecoflow_stale_only_does_not_create_high_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {
            "ecoflow_energy_overview": {
                **_ecoflow(80),
                "warning_count_by_severity": 2,
                "warnings": [{"code": "stale_value", "severity": "warning"}],
            }
        },
    )

    result = controller.run_once()

    assert result["created_count"] == 0


def test_ignored_ha_entity_does_not_create_critical_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {"home_assistant_get_problems": {"critical_count": 0, "critical": [], "warning": [], "informational": []}},
    )

    result = controller.run_once()

    assert not any(alert["rule_id"] == "home_assistant_critical" for alert in result["alerts"])


def test_non_ignored_ha_critical_creates_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {
            "home_assistant_get_problems": {
                "critical_count": 1,
                "critical": [{"entity_id": "sensor.bad", "state": "unavailable"}],
                "warning": [],
                "informational": [],
            }
        },
    )

    result = controller.run_once()

    assert any(alert["rule_id"] == "home_assistant_critical" for alert in result["alerts"])


def test_gmail_security_email_creates_high_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {
            "gmail_unread_recent": {
                "providers": [
                    {
                        "provider": "gmail",
                        "connected": True,
                        "emails": [{"sender": "GitHub", "subject": "A third-party OAuth application has been added"}],
                    }
                ]
            }
        },
    )

    result = controller.run_once()

    assert any(alert["rule_id"] == "security_email" for alert in result["alerts"])


def test_gmail_marketing_email_does_not_create_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {
            "gmail_unread_recent": {
                "providers": [
                    {
                        "provider": "gmail",
                        "connected": True,
                        "emails": [{"sender": "LOTTO24", "subject": "Jackpot Angebot"}],
                    }
                ]
            }
        },
    )

    result = controller.run_once()

    assert not any(alert["rule_id"] == "security_email" for alert in result["alerts"])


def test_timetree_today_event_creates_info_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(
        monkeypatch,
        tmp_path,
        {"timetree_today": {"count": 1, "events": [{"title": "Familienessen"}]}},
    )

    result = controller.run_once()

    assert any(alert["rule_id"] == "timetree_today" and alert["severity"] == "info" for alert in result["alerts"])


def test_cooldown_suppresses_duplicate_alert(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path, {"ecoflow_energy_overview": _ecoflow(18)})

    first = controller.run_once()
    second = controller.run_once()

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["suppressed_count"] == 1


def test_acknowledge_alert_works(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path, {"ecoflow_energy_overview": _ecoflow(18)})
    alert_id = controller.run_once()["alerts"][0]["id"]

    acknowledged = controller.acknowledge_alert(alert_id)

    assert acknowledged["acknowledged"] is True


def test_clear_alerts_works(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path, {"ecoflow_energy_overview": _ecoflow(18)})
    controller.run_once()

    result = controller.clear_alerts()

    assert result["cleared"] is True
    assert controller.list_alerts() == []


def test_watchers_status_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WATCHER_ALERTS_FILE", str(tmp_path / "alerts.json"))

    response = client.get("/assistant/watchers/status")

    assert response.status_code == 200
    assert "enabled" in response.json()


def test_watchers_run_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WATCHER_ALERTS_FILE", str(tmp_path / "alerts.json"))

    response = client.post("/assistant/watchers/run")

    assert response.status_code == 200


def test_watchers_alerts_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WATCHER_ALERTS_FILE", str(tmp_path / "alerts.json"))

    response = client.get("/assistant/watchers/alerts")

    assert response.status_code == 200


def test_dashboard_still_returns_200() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200


def _controller(monkeypatch, tmp_path, tool_results: dict[str, dict[str, Any]]) -> WatcherController:
    monkeypatch.setenv("WATCHER_ALERTS_FILE", str(tmp_path / "alerts.json"))
    rules_file = tmp_path / "watcher_rules.json"
    rules_file.write_text(
        __import__("json").dumps({"rules": [_rule_for_tool(name) for name in tool_results]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("WATCHER_RULES_FILE", str(rules_file))
    registry = ToolRegistry()
    for name, result in tool_results.items():
        registry.register(name, name, ActionRisk.GREEN, lambda result=result: result)
    return WatcherController(registry=registry)


def _rule_for_tool(tool_name: str) -> dict[str, Any]:
    if tool_name == "ecoflow_energy_overview":
        return {
            "id": "ecoflow_low_battery",
            "enabled": True,
            "type": "ecoflow_low_battery",
            "threshold_percent": 20,
            "severity": "high",
            "cooldown_minutes": 60,
        }
    if tool_name == "home_assistant_get_problems":
        return {
            "id": "home_assistant_critical",
            "enabled": True,
            "type": "home_assistant_critical",
            "severity": "critical",
            "cooldown_minutes": 30,
        }
    if tool_name == "gmail_unread_recent":
        return {
            "id": "security_email",
            "enabled": True,
            "type": "gmail_security_email",
            "severity": "high",
            "cooldown_minutes": 120,
        }
    if tool_name == "timetree_today":
        return {
            "id": "timetree_today",
            "enabled": True,
            "type": "timetree_today_events",
            "severity": "info",
            "cooldown_minutes": 240,
        }
    return {"id": tool_name, "enabled": True, "type": tool_name}


def _ecoflow(soc: float) -> dict[str, Any]:
    return {
        "soc_percent": soc,
        "human_status": {"overall": "ok", "headline": "EcoFlow laeuft.", "details": [f"Batterie: {soc} %"]},
        "critical_count": 0,
        "warning_count_by_severity": 0,
        "warnings": [],
    }
