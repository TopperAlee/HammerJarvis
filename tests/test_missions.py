from typing import Any

from fastapi.testclient import TestClient

from app.agent.permissions import ActionRisk
from app.assistant.missions import MissionController
from app.assistant.tool_registry import ToolRegistry
from app.main import app


client = TestClient(app)


def test_detect_mission_detects_daily_briefing() -> None:
    controller = MissionController(registry=_mission_registry([]))

    assert controller.detect_mission("Gibt es heute etwas Wichtiges?") == "daily_briefing"


def test_daily_briefing_calls_all_required_green_tools() -> None:
    calls: list[str] = []
    result = MissionController(registry=_mission_registry(calls)).run_mission(
        "daily_briefing",
        "Tagesstatus",
    )

    assert calls == [
        "gmail_unread_recent",
        "timetree_today",
        "home_assistant_get_problems",
        "ecoflow_energy_overview",
    ]
    assert result["mission"] == "daily_briefing"
    assert result["risk"] == "GREEN"
    assert "Wichtig zuerst" in result["answer"]


def test_home_check_calls_home_assistant_and_ecoflow() -> None:
    calls: list[str] = []

    MissionController(registry=_mission_registry(calls)).run_mission("home_check", "Hauscheck")

    assert calls == ["home_assistant_get_problems", "ecoflow_energy_overview"]


def test_energy_check_calls_ecoflow_only() -> None:
    calls: list[str] = []
    result = MissionController(registry=_mission_registry(calls)).run_mission(
        "energy_check",
        "Energiecheck",
    )

    assert calls == ["ecoflow_energy_overview"]
    assert "Batterieleistung roh" in result["answer"]


def test_inbox_briefing_calls_gmail_unread() -> None:
    calls: list[str] = []
    result = MissionController(registry=_mission_registry(calls)).run_mission(
        "inbox_briefing",
        "Posteingang",
    )

    assert calls == ["gmail_unread_recent"]
    assert "Gmail-Nachrichten" in result["answer"]


def test_family_calendar_briefing_calls_timetree_today() -> None:
    calls: list[str] = []
    result = MissionController(registry=_mission_registry(calls)).run_mission(
        "family_calendar_briefing",
        "Familienkalender",
    )

    assert calls == ["timetree_today"]
    assert "TimeTree-Termine" in result["answer"]


def test_missions_do_not_execute_yellow_or_red_tools() -> None:
    registry = ToolRegistry()
    registry.register(
        "yellow_tool",
        "yellow",
        ActionRisk.YELLOW,
        lambda: {"executed": True},
    )
    registry.register(
        "red_tool",
        "red",
        ActionRisk.RED,
        lambda: {"executed": True},
    )
    controller = MissionController(registry=registry)

    yellow = controller._execute_green_tool("yellow_tool")
    red = controller._execute_green_tool("red_tool")

    assert yellow["confirmation_required"] is True
    assert red["blocked"] is True


def test_assistant_missions_endpoint_returns_200() -> None:
    response = client.get("/assistant/missions")

    assert response.status_code == 200
    assert response.json()["missions"][0]["name"] == "daily_briefing"


def test_assistant_mission_run_returns_daily_briefing(monkeypatch) -> None:
    monkeypatch.setattr("app.assistant.missions.MissionController.run_daily_briefing", lambda self: _mission_payload("daily_briefing"))

    response = client.post("/assistant/mission/run", json={"mission": "daily_briefing"})

    assert response.status_code == 200
    assert response.json()["mission"] == "daily_briefing"


def test_dashboard_still_returns_200() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200


def _mission_registry(calls: list[str]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "gmail_unread_recent",
        "gmail",
        ActionRisk.GREEN,
        lambda: calls.append("gmail_unread_recent") or _email_result(),
    )
    registry.register(
        "timetree_today",
        "timetree",
        ActionRisk.GREEN,
        lambda: calls.append("timetree_today") or _timetree_result(),
    )
    registry.register(
        "home_assistant_get_problems",
        "ha",
        ActionRisk.GREEN,
        lambda: calls.append("home_assistant_get_problems") or _ha_result(),
    )
    registry.register(
        "ecoflow_energy_overview",
        "ecoflow",
        ActionRisk.GREEN,
        lambda: calls.append("ecoflow_energy_overview") or _ecoflow_result(),
    )
    return registry


def _mission_payload(name: str) -> dict[str, Any]:
    return {
        "mission": name,
        "answer": "ok",
        "tool_results": {},
        "risk": "GREEN",
        "actions_taken": [],
        "suggested_next_steps": [],
    }


def _email_result() -> dict[str, Any]:
    return {
        "total_email_count": 2,
        "unread_count": 2,
        "providers": [
            {
                "provider": "gmail",
                "connected": True,
                "emails": [
                    {"sender": "Max", "subject": "Termin"},
                    {"sender": "Lisa", "subject": "Update"},
                ],
            }
        ],
        "message": "Ich habe 2 Gmail-Nachrichten gefunden.",
    }


def _timetree_result() -> dict[str, Any]:
    return {
        "provider": "timetree",
        "enabled": True,
        "connected": True,
        "events": [{"title": "Familienessen", "start": "2026-06-05T18:00:00", "all_day": False}],
    }


def _ha_result() -> dict[str, Any]:
    return {
        "critical_count": 1,
        "warning_count": 1,
        "informational_count": 0,
        "critical": [{"entity_id": "sensor.bad", "state": "unavailable"}],
        "warning": [{"entity_id": "sensor.warn", "state": "unknown"}],
        "informational": [],
    }


def _ecoflow_result() -> dict[str, Any]:
    return {
        "battery_power_w": -43.4,
        "human_status": {
            "headline": "EcoFlow ist erreichbar.",
            "details": ["Batterie: 45 %", "PV-Leistung: 0 W"],
        },
        "battery_status": {"raw_value_w": -43.4, "sign_convention": "unknown"},
        "warnings": [],
    }
