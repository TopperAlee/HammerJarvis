from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.agent.permissions import ActionRisk
from app.assistant.actions.action_executor import ActionExecutor
from app.assistant.actions.action_planner import ActionPlanner
from app.assistant.actions.pending_action_store import PendingActionStore, pending_action_store
from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.tool_registry import ToolRegistry
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    pending_action_store.clear()


def test_create_pending_green_action() -> None:
    action = pending_action_store.create_action(
        {
            "title": "Diagnose",
            "description": "Diagnose ausführen",
            "tool_name": "home_assistant_get_problems",
            "arguments": {},
            "risk": "GREEN",
            "source": "hauscheck",
        }
    )

    assert action["status"] == "pending"
    assert action["requires_confirmation"] is False
    assert pending_action_store.list_pending_actions()[0]["id"] == action["id"]


def test_execute_green_action_through_tool_registry() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register("test_green", "test", ActionRisk.GREEN, lambda: calls.append("test_green") or {"ok": True})
    action = pending_action_store.create_action(
        {"title": "Test", "description": "Test", "tool_name": "test_green", "arguments": {}, "risk": "GREEN", "source": "chat"}
    )

    result = ActionExecutor(registry=registry).execute(action["id"])

    assert result["status"] == "executed"
    assert calls == ["test_green"]
    assert pending_action_store.get_action(action["id"])["status"] == "executed"


def test_yellow_action_requires_confirmation() -> None:
    registry = ToolRegistry()
    registry.register("yellow_tool", "yellow", ActionRisk.YELLOW, lambda: {"ok": True}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {"title": "Gelb", "description": "Gelb", "tool_name": "yellow_tool", "arguments": {}, "risk": "YELLOW", "source": "chat"}
    )

    result = ActionExecutor(registry=registry).execute(action["id"], confirm=False)

    assert result["confirmation_required"] is True
    assert pending_action_store.get_action(action["id"])["status"] == "pending"


def test_yellow_action_executes_only_with_confirm_true() -> None:
    registry = ToolRegistry()
    registry.register("yellow_tool", "yellow", ActionRisk.YELLOW, lambda: {"ok": True}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {"title": "Gelb", "description": "Gelb", "tool_name": "yellow_tool", "arguments": {}, "risk": "YELLOW", "source": "chat"}
    )

    result = ActionExecutor(registry=registry).execute(action["id"], confirm=True)

    assert result["status"] == "executed"
    assert result["result"]["executed"] is True


def test_red_action_is_blocked() -> None:
    registry = ToolRegistry()
    registry.register("red_tool", "red", ActionRisk.RED, lambda: {"ok": True})
    action = pending_action_store.create_action(
        {"title": "Rot", "description": "Rot", "tool_name": "red_tool", "arguments": {}, "risk": "RED", "source": "chat"}
    )

    result = ActionExecutor(registry=registry).execute(action["id"], confirm=True)

    assert result["status"] == "blocked"
    assert pending_action_store.get_action(action["id"])["status"] == "blocked"


def test_expired_actions_are_not_executed() -> None:
    store = PendingActionStore(default_ttl_minutes=-1)
    action = store.create_action(
        {"title": "Alt", "description": "Alt", "tool_name": "home_assistant_get_problems", "arguments": {}, "risk": "GREEN", "source": "chat"}
    )

    result = ActionExecutor(store=store).execute(action["id"])

    assert result["status"] == "expired"


def test_hauscheck_creates_pending_diagnostic_actions() -> None:
    mission_result = {
        "mission": "home_check",
        "answer": "Home Assistant Backup warning",
        "tool_results": {
            "home_assistant_get_problems": {
                "warning": [{"entity_id": "binary_sensor.backup", "state": "unknown"}],
            },
            "ecoflow_energy_overview": {
                "warnings": [{"code": "stale_value", "message": "Der Tageswert ist veraltet."}],
                "human_status": {"headline": "EcoFlow läuft, aber Werte sind veraltet."},
            },
        },
    }

    actions = ActionPlanner().create_actions_from_mission(mission_result)

    titles = {action["title"] for action in actions}
    assert "Diagnosebericht erstellen" in titles
    assert "Home-Assistant-Backup-Warnungen analysieren" in titles
    assert "EcoFlow-Diagnosebericht erstellen" in titles


def test_hauscheck_with_soc_10_creates_yellow_low_battery_action(monkeypatch) -> None:
    monkeypatch.setenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20")
    mission_result = {
        "mission": "home_check",
        "answer": "Hauscheck",
        "tool_results": {
            "home_assistant_get_problems": {"warning": []},
            "ecoflow_energy_overview": {"soc_percent": 10, "warnings": []},
        },
    }

    actions = ActionPlanner().create_actions_from_mission(mission_result)
    low_battery = actions[0]

    assert low_battery["title"] == "EcoFlow-Batterie kritisch niedrig prüfen"
    assert low_battery["risk"] == "YELLOW"
    assert low_battery["tool_name"] == "energy_saving_recommendations"
    assert low_battery["arguments"] == {"soc_percent": 10.0, "source": "ecoflow"}
    assert low_battery["requires_confirmation"] is True


def test_hauscheck_answer_highlights_low_ecoflow_battery(monkeypatch) -> None:
    monkeypatch.setenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20")
    registry = ToolRegistry()
    registry.register(
        "home_assistant_get_problems",
        "ha",
        ActionRisk.GREEN,
        lambda: {"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
    )
    registry.register(
        "ecoflow_energy_overview",
        "ecoflow",
        ActionRisk.GREEN,
        lambda: {"soc_percent": 10, "warnings": [], "human_status": {"headline": "EcoFlow ist erreichbar.", "details": ["Batterie: 10 %"]}},
    )

    result = AssistantOrchestrator(registry=registry).handle_message("Hauscheck")

    assert "Warnung: EcoFlow-Batterie ist niedrig: 10 %." in result["answer"]
    assert "1. [GELB] EcoFlow-Batterie kritisch niedrig prüfen" in result["answer"]


def test_orchestrator_executes_first_pending_action() -> None:
    registry = ToolRegistry()
    registry.register("test_green", "test", ActionRisk.GREEN, lambda: {"ok": True})
    action = pending_action_store.create_action(
        {"title": "Test", "description": "Test", "tool_name": "test_green", "arguments": {}, "risk": "GREEN", "source": "chat"}
    )
    pending_action_store.present_actions([action], source="chat")

    result = AssistantOrchestrator(registry=registry).handle_message("Führe Aktion 1 aus")

    assert result["tool"] == "action_execute"
    assert result["result"]["status"] == "executed"


def test_yellow_action_message_requires_explicit_confirmation() -> None:
    registry = ToolRegistry()
    registry.register("yellow_tool", "yellow", ActionRisk.YELLOW, lambda: {"ok": True}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {"title": "Gelb", "description": "Gelb", "tool_name": "yellow_tool", "arguments": {}, "risk": "YELLOW", "source": "chat"}
    )
    pending_action_store.present_actions([action], source="chat")

    result = AssistantOrchestrator(registry=registry).handle_message("Führe Aktion 1 aus")

    assert result["result"]["confirmation_required"] is True
    assert result["answer"] == "Diese Aktion benötigt eine Bestätigung. Sag: 'Bestätige Aktion 1', wenn ich fortfahren soll."


def test_yellow_action_executes_after_confirmation() -> None:
    registry = ToolRegistry()
    registry.register("energy_saving_recommendations", "energy", ActionRisk.YELLOW, lambda soc_percent=None, source="ecoflow": {"recommendations": ["ok"]}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {
            "title": "EcoFlow-Batterie kritisch niedrig prüfen",
            "description": "test",
            "tool_name": "energy_saving_recommendations",
            "arguments": {"soc_percent": 10, "source": "ecoflow"},
            "risk": "YELLOW",
            "source": "hauscheck",
            "requires_confirmation": True,
        }
    )
    pending_action_store.present_actions([action], source="hauscheck")

    result = AssistantOrchestrator(registry=registry).handle_message("Bestätige Aktion 1")

    assert result["result"]["status"] == "executed"


def test_confirming_recent_smart_home_action_does_not_execute_stale_hauscheck_action() -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(
        "energy_saving_recommendations",
        "energy",
        ActionRisk.YELLOW,
        lambda soc_percent=None, source="ecoflow": executed.append("ecoflow") or {"message": "EcoFlow"},
        requires_confirmation=True,
    )
    registry.register(
        "hauscheck_diagnostic_report",
        "report",
        ActionRisk.GREEN,
        lambda: executed.append("report") or {"created": True, "path": "hauscheck.md", "message": "Diagnosebericht wurde erstellt."},
    )
    registry.register(
        "home_assistant_get_problems",
        "ha",
        ActionRisk.GREEN,
        lambda: executed.append("backup") or {"message": "Backup"},
    )
    registry.register(
        "home_assistant_resolve_control_intent",
        "resolve",
        ActionRisk.GREEN,
        lambda command: {
            "title": "Flur Licht ausschalten",
            "entity_id": "light.flur",
            "action": "turn_off",
            "risk": "YELLOW",
            "parameters": {},
        },
    )
    registry.register(
        "home_assistant_execute_control_action",
        "execute",
        ActionRisk.YELLOW,
        lambda entity_id, action, parameters=None: executed.append(f"{entity_id}:{action}") or {"message": "Flur Licht wurde ausgeschaltet."},
        requires_confirmation=True,
    )
    for action in (
        {
            "title": "EcoFlow-Batterie kritisch niedrig prüfen",
            "tool_name": "energy_saving_recommendations",
            "arguments": {"soc_percent": 10, "source": "ecoflow"},
            "risk": "YELLOW",
            "source": "hauscheck",
            "requires_confirmation": True,
        },
        {"title": "Diagnosebericht erstellen", "tool_name": "hauscheck_diagnostic_report", "arguments": {}, "risk": "GREEN", "source": "hauscheck"},
        {"title": "Home-Assistant-Backup-Warnungen analysieren", "tool_name": "home_assistant_get_problems", "arguments": {}, "risk": "GREEN", "source": "hauscheck"},
    ):
        pending_action_store.create_action(action)

    orchestrator = AssistantOrchestrator(registry=registry)
    prepared = orchestrator.handle_message("Jarvis, Flur Licht ausschalten.")
    confirmed = orchestrator.handle_message("Bestätige Aktion 1")

    assert "Bestätige Aktion 1" in prepared["answer"]
    assert confirmed["result"]["action"]["title"] == "Flur Licht ausschalten"
    assert executed == ["light.flur:turn_off"]
    assert pending_action_store.list_pending_actions()[0]["title"] == "EcoFlow-Batterie kritisch niedrig prüfen"


def test_hauscheck_display_context_action_2_executes_second_action() -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register("first_tool", "first", ActionRisk.GREEN, lambda: executed.append("first") or {"message": "first"})
    registry.register("second_tool", "second", ActionRisk.GREEN, lambda: executed.append("second") or {"created": True, "path": "diagnose.md", "message": "Diagnosebericht wurde erstellt."})
    actions = [
        pending_action_store.create_action({"title": "EcoFlow prüfen", "tool_name": "first_tool", "arguments": {}, "risk": "YELLOW", "source": "hauscheck", "requires_confirmation": True}),
        pending_action_store.create_action({"title": "Diagnosebericht erstellen", "tool_name": "second_tool", "arguments": {}, "risk": "GREEN", "source": "hauscheck"}),
    ]
    pending_action_store.present_actions(actions, source="hauscheck")

    result = AssistantOrchestrator(registry=registry).handle_message("Führe Aktion 2 aus")

    assert result["result"]["action"]["title"] == "Diagnosebericht erstellen"
    assert executed == ["second"]


def test_yes_confirms_only_single_recent_presented_action() -> None:
    registry = ToolRegistry()
    registry.register("yellow_tool", "yellow", ActionRisk.YELLOW, lambda: {"message": "ok"}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {"title": "Gelb", "description": "Gelb", "tool_name": "yellow_tool", "arguments": {}, "risk": "YELLOW", "source": "chat", "requires_confirmation": True}
    )
    pending_action_store.present_actions([action], source="chat")

    result = AssistantOrchestrator(registry=registry).handle_message("Ja")

    assert result["result"]["status"] == "executed"
    assert result["result"]["action"]["title"] == "Gelb"


def test_yes_with_multiple_recent_actions_asks_for_clarification() -> None:
    actions = [
        pending_action_store.create_action({"title": "A", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"}),
        pending_action_store.create_action({"title": "B", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"}),
    ]
    pending_action_store.present_actions(actions, source="test")

    result = AssistantOrchestrator().handle_message("Ja")

    assert "welche Aktion" in result["answer"]


def test_confirm_without_recent_context_is_ambiguous() -> None:
    pending_action_store.create_action({"title": "A", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})

    result = AssistantOrchestrator().handle_message("Bestätige Aktion 1")

    assert "nicht eindeutig zuordnen" in result["answer"]


def test_pending_endpoint_returns_display_indices() -> None:
    pending_action_store.create_action({"title": "A", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})
    pending_action_store.create_action({"title": "B", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})

    response = client.get("/assistant/actions/pending")

    assert response.status_code == 200
    assert [action["display_index"] for action in response.json()["actions"]] == [1, 2]


def test_ambiguous_plural_confirmation_preserves_recent_smart_home_context() -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(
        "energy_saving_recommendations",
        "energy",
        ActionRisk.YELLOW,
        lambda soc_percent=None, source="ecoflow": executed.append("ecoflow") or {"message": "EcoFlow"},
        requires_confirmation=True,
    )
    registry.register(
        "home_assistant_resolve_control_intent",
        "resolve",
        ActionRisk.GREEN,
        lambda command: {
            "title": "Flur Licht einschalten",
            "entity_id": "light.flur",
            "action": "turn_on",
            "risk": "YELLOW",
            "parameters": {},
        },
    )
    registry.register(
        "home_assistant_execute_control_action",
        "execute",
        ActionRisk.YELLOW,
        lambda entity_id, action, parameters=None: executed.append(f"{entity_id}:{action}") or {"message": "Flur Licht wurde eingeschaltet."},
        requires_confirmation=True,
    )
    pending_action_store.create_action(
        {
            "title": "EcoFlow-Batterie kritisch niedrig prüfen",
            "tool_name": "energy_saving_recommendations",
            "arguments": {"soc_percent": 10, "source": "ecoflow"},
            "risk": "YELLOW",
            "source": "hauscheck",
            "requires_confirmation": True,
        }
    )

    orchestrator = AssistantOrchestrator(registry=registry)
    prepared = orchestrator.handle_message("Jarvis, Flur Licht einschalten.")
    ambiguous = orchestrator.handle_message("bestätige Aktionen")
    confirmed = orchestrator.handle_message("bestätige Aktion 1")

    assert "Bestätige Aktion 1" in prepared["answer"]
    assert "Meinst du Aktion 1: Flur Licht einschalten" in ambiguous["answer"]
    assert confirmed["result"]["action"]["title"] == "Flur Licht einschalten"
    assert executed == ["light.flur:turn_on"]


def test_presented_context_contains_lifecycle_metadata() -> None:
    action = pending_action_store.create_action({"title": "A", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})

    pending_action_store.present_actions([action], source="test")
    context = pending_action_store.get_active_context()

    assert context is not None
    assert context["context_id"]
    assert context["presented_action_ids"] == [action["id"]]
    assert context["source"] == "test"
    assert context["created_at"]
    assert context["expires_at"]
    assert context["consumed"] is False


def test_executed_action_consumes_presented_context() -> None:
    registry = ToolRegistry()
    registry.register("test_green", "test", ActionRisk.GREEN, lambda: {"ok": True})
    action = pending_action_store.create_action({"title": "Test", "tool_name": "test_green", "arguments": {}, "risk": "GREEN", "source": "test"})
    pending_action_store.present_actions([action], source="test")

    AssistantOrchestrator(registry=registry).handle_message("Führe Aktion 1 aus")

    context = pending_action_store.get_active_context()
    assert context is None or context["consumed"] is True


def test_plural_confirmation_with_one_active_action_asks_for_exact_number() -> None:
    registry = ToolRegistry()
    registry.register("yellow_tool", "yellow", ActionRisk.YELLOW, lambda: {"message": "ok"}, requires_confirmation=True)
    action = pending_action_store.create_action(
        {"title": "Flur Licht einschalten", "tool_name": "yellow_tool", "arguments": {}, "risk": "YELLOW", "source": "smart_home", "requires_confirmation": True}
    )
    pending_action_store.present_actions([action], source="smart_home")

    result = AssistantOrchestrator(registry=registry).handle_message("bestätige alle Aktionen")

    assert "Meinst du Aktion 1: Flur Licht einschalten" in result["answer"]
    assert pending_action_store.get_active_context()["presented_action_ids"] == [action["id"]]


def test_show_open_actions_creates_fresh_display_context() -> None:
    first = pending_action_store.create_action({"title": "A", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})
    second = pending_action_store.create_action({"title": "B", "tool_name": "test", "arguments": {}, "risk": "GREEN", "source": "test"})

    result = AssistantOrchestrator().handle_message("zeige offene Aktionen")

    assert "Mögliche nächste Aktionen" in result["answer"]
    assert pending_action_store.get_active_context()["presented_action_ids"] == [first["id"], second["id"]]


def test_confirmed_yellow_energy_action_returns_recommendations() -> None:
    action = pending_action_store.create_action(
        {
            "title": "EcoFlow-Batterie kritisch niedrig prÃ¼fen",
            "description": "test",
            "tool_name": "energy_saving_recommendations",
            "arguments": {"soc_percent": 10, "source": "ecoflow"},
            "risk": "YELLOW",
            "source": "hauscheck",
            "requires_confirmation": True,
        }
    )
    pending_action_store.present_actions([action], source="hauscheck")

    result = AssistantOrchestrator().handle_message("BestÃ¤tige Aktion 1")

    assert "EcoFlow-Batterie kritisch niedrig: 10 %" in result["answer"]
    assert "Empfohlene sichere Maßnahmen:" in result["answer"]
    assert "Ich habe nichts automatisch geschaltet." in result["answer"]
    assert "Diese Aktion wurde erst nach deiner Bestätigung ausgeführt." in result["answer"]
    assert result["result"]["result"]["result"]["recommendations"]


def test_action_executor_returns_full_tool_result() -> None:
    action = pending_action_store.create_action(
        {
            "title": "EcoFlow-Batterie kritisch niedrig prÃ¼fen",
            "description": "test",
            "tool_name": "energy_saving_recommendations",
            "arguments": {"soc_percent": 10, "source": "ecoflow"},
            "risk": "YELLOW",
            "source": "hauscheck",
            "requires_confirmation": True,
        }
    )

    result = ActionExecutor().execute(action["id"], confirm=True)

    assert result["status"] == "executed"
    assert result["action"]["title"] == "EcoFlow-Batterie kritisch niedrig prüfen"
    assert result["result"]["result"]["headline"] == "EcoFlow-Batterie kritisch niedrig: 10 %"
    assert result["message"] == "Ich habe sichere Energiesparmaßnahmen vorgeschlagen und nichts automatisch geschaltet."


def test_green_file_action_response_shows_created_path(tmp_path: Path) -> None:
    output = tmp_path / "hauscheck_diagnose.md"
    registry = ToolRegistry()
    registry.register(
        "file_create_markdown",
        "markdown",
        ActionRisk.GREEN,
        lambda title, content, filename=None: {
            "created": True,
            "file_type": "md",
            "filename": output.name,
            "path": str(output),
            "message": "Diagnosebericht wurde erstellt.",
        },
    )
    action = pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "file_create_markdown",
            "arguments": {"title": "Hauscheck", "content": "ok", "filename": output.name},
            "risk": "GREEN",
            "source": "hauscheck",
        }
    )
    pending_action_store.present_actions([action], source="hauscheck")

    result = AssistantOrchestrator(registry=registry).handle_message("FÃ¼hre Aktion 1 aus")

    assert "Diagnosebericht wurde erstellt:" in result["answer"]
    assert output.name in result["answer"]
    assert str(output) in result["answer"]


def test_energy_saving_recommendations_does_not_switch_devices() -> None:
    result = ToolRegistry().execute_tool(
        "energy_saving_recommendations",
        {"soc_percent": 10, "source": "ecoflow"},
        confirm=True,
    )

    recommendations = result["result"]["recommendations"]
    assert result["executed"] is True
    assert result["risk"] == "YELLOW"
    assert result["result"]["switching_performed"] is False
    assert any("Verbraucher" in item for item in recommendations)


def test_action_execution_writes_audit_log(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr("app.logging_utils.audit.LOG_PATH", log_file)
    monkeypatch.setattr("app.assistant.actions.action_executor.LOG_PATH", log_file)
    registry = ToolRegistry()
    registry.register("test_green", "test", ActionRisk.GREEN, lambda: {"ok": True})
    action = pending_action_store.create_action(
        {"title": "Test", "description": "Test", "tool_name": "test_green", "arguments": {}, "risk": "GREEN", "source": "chat"}
    )

    ActionExecutor(registry=registry).execute(action["id"])

    assert "assistant_action_start" in log_file.read_text(encoding="utf-8")
    assert "assistant_action_end" in log_file.read_text(encoding="utf-8")


def test_action_endpoints_and_dashboard_still_work() -> None:
    action = pending_action_store.create_action(
        {"title": "Fähigkeiten", "description": "Fähigkeiten", "tool_name": "assistant_capabilities", "arguments": {}, "risk": "GREEN", "source": "chat"}
    )

    pending = client.get("/assistant/actions/pending")
    executed = client.post(f"/assistant/actions/{action['id']}/execute", json={"confirm": False})
    dashboard = client.get("/dashboard")

    assert pending.status_code == 200
    assert executed.status_code == 200
    assert dashboard.status_code == 200


def test_pending_action_labels_are_utf8() -> None:
    pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "hauscheck_diagnostic_report",
            "arguments": {},
            "risk": "GREEN",
            "source": "hauscheck",
        }
    )

    result = AssistantOrchestrator().handle_message("Welche Aktionen stehen aus?")

    assert "Mögliche nächste Aktionen:" in result["answer"]
    assert "[GRÜN]" in result["answer"]
    assert "MÃ" not in result["answer"]


def test_numbered_green_action_text_executes_pending_action() -> None:
    registry = ToolRegistry()
    registry.register("first_tool", "first", ActionRisk.GREEN, lambda: {"ok": "first"})
    registry.register("second_tool", "second", ActionRisk.GREEN, lambda: {"ok": "second"})
    pending_action_store.create_action(
        {"title": "Erste Aktion", "description": "test", "tool_name": "first_tool", "arguments": {}, "risk": "GREEN", "source": "test"}
    )
    pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "second_tool",
            "arguments": {},
            "risk": "GREEN",
            "source": "test",
        }
    )

    result = AssistantOrchestrator(registry=registry).handle_message("2. [GRÜN] Diagnosebericht erstellen")

    assert result["tool"] == "action_execute"
    assert result["result"]["status"] == "executed"
    assert result["result"]["result"]["result"]["ok"] == "second"


def test_numbered_english_green_action_text_executes_pending_action() -> None:
    registry = ToolRegistry()
    registry.register("second_tool", "second", ActionRisk.GREEN, lambda: {"ok": "second"})
    pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "second_tool",
            "arguments": {},
            "risk": "GREEN",
            "source": "test",
        }
    )

    result = AssistantOrchestrator(registry=registry).handle_message("1. [GREEN] Diagnosebericht erstellen")

    assert result["tool"] == "action_execute"
    assert result["result"]["status"] == "executed"


def test_action_title_text_executes_matching_pending_action() -> None:
    registry = ToolRegistry()
    registry.register("report_tool", "report", ActionRisk.GREEN, lambda: {"created": True, "path": "report.md", "message": "Diagnosebericht wurde erstellt."})
    pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "report_tool",
            "arguments": {},
            "risk": "GREEN",
            "source": "test",
        }
    )

    result = AssistantOrchestrator(registry=registry).handle_message("Diagnosebericht erstellen")

    assert result["tool"] == "action_execute"
    assert result["result"]["status"] == "executed"


def test_hauscheck_diagnostic_report_creates_real_markdown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    registry = ToolRegistry()
    registry.register(
        "home_assistant_get_problems",
        "ha",
        ActionRisk.GREEN,
        lambda: {
            "critical_count": 0,
            "warning_count": 1,
            "informational_count": 2,
            "critical": [],
            "warning": [{"entity_id": "binary_sensor.backup", "state": "unknown", "friendly_name": "Backup"}],
            "informational": [],
        },
    )
    registry.register(
        "ecoflow_energy_overview",
        "ecoflow",
        ActionRisk.GREEN,
        lambda: {
            "soc_percent": 10,
            "pv_power_w": 0,
            "smart_meter_w": 11,
            "grid_power_w": 43,
            "battery_power_w": -43,
            "warnings": [{"message": "Der Tageswert Solarenergie heute ist veraltet."}],
        },
    )

    result = registry.execute_tool("hauscheck_diagnostic_report", {})

    assert result["executed"] is True
    report = result["result"]
    assert report["created"] is True
    path = Path(report["path"])
    content = path.read_text(encoding="utf-8")
    assert "Home Assistant: 0 kritisch, 1 Warnungen, 2 Infos" in content
    assert "binary_sensor.backup" in content
    assert "Batterie: 10 %" in content
    assert "PV-Leistung: 0 W" in content
    assert "LAN Smart Meter: 11 W" in content
    assert "Netzleistung System: 43 W" in content
    assert "Batterieleistung roh: -43 W" in content
    assert "[Wert aus Tool]" not in content
    assert "[falls verknüpft]" not in content
    assert "[Aktuelle Gerätestatus]" not in content


def test_dashboard_html_declares_utf8() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")

    assert '<meta charset="UTF-8">' in html


def test_diagnostic_report_soc_10_is_critical(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    monkeypatch.setenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20")
    registry = _diagnostic_registry(
        soc=10,
        ha={"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
        eco_warnings=[],
    )

    report = registry.execute_tool("hauscheck_diagnostic_report", {})["result"]
    content = Path(report["path"]).read_text(encoding="utf-8")

    assert report["status"] == "KRITISCH"
    assert "Status: KRITISCH" in content
    assert "EcoFlow-Batterie kritisch niedrig: 10 %" in content


def test_diagnostic_report_soc_18_is_warning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    monkeypatch.setenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20")
    registry = _diagnostic_registry(
        soc=18,
        ha={"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
        eco_warnings=[],
    )

    report = registry.execute_tool("hauscheck_diagnostic_report", {})["result"]
    content = Path(report["path"]).read_text(encoding="utf-8")

    assert report["status"] == "WARNUNG"
    assert "EcoFlow-Batterie niedrig: 18 %" in content


def test_diagnostic_report_stale_only_is_warning_not_critical(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    registry = _diagnostic_registry(
        soc=63,
        ha={"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
        eco_warnings=[
            {"code": "stale_value", "severity": "warning", "message": "Der Tageswert Verbrauch heute ist veraltet."},
            {"code": "stale_value", "severity": "warning", "message": "Der Tageswert Solarenergie heute ist veraltet."},
        ],
    )

    report = registry.execute_tool("hauscheck_diagnostic_report", {})["result"]

    assert report["status"] == "WARNUNG"
    assert "KRITISCH" not in report["summary"].split(".", maxsplit=1)[0]


def test_diagnostic_report_ignored_entity_is_not_critical(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    registry = _diagnostic_registry(
        soc=63,
        ha={"critical_count": 0, "warning_count": 0, "informational_count": 1, "critical": [], "warning": [], "informational": []},
        eco_warnings=[
            {
                "code": "entity_ignored",
                "severity": "info",
                "message": "Bekannte optionale EcoFlow-Entity ignoriert: sensor.optional",
                "source_entity_id": "sensor.optional",
            }
        ],
    )

    report = registry.execute_tool("hauscheck_diagnostic_report", {})["result"]
    content = Path(report["path"]).read_text(encoding="utf-8")

    assert report["status"] == "OK"
    assert "## Ignorierte bekannte Entities" in content
    assert "sensor.optional" in content
    assert "Status: KRITISCH" not in content


def test_diagnostic_report_contains_safety_notice_and_order(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    registry = _diagnostic_registry(
        soc=10,
        ha={"critical_count": 0, "warning_count": 1, "informational_count": 0, "critical": [], "warning": [{"entity_id": "sensor.backup"}], "informational": []},
        eco_warnings=[{"code": "stale_value", "message": "Der Tageswert Solarenergie heute ist veraltet."}],
    )

    report = registry.execute_tool("hauscheck_diagnostic_report", {})["result"]
    content = Path(report["path"]).read_text(encoding="utf-8")

    assert "Jarvis hat nichts automatisch geschaltet oder verändert." in content
    assert content.index("EcoFlow-Batterie kritisch niedrig: 10 %") < content.index("Der Tageswert Solarenergie heute ist veraltet.")
    assert "Die Richtung wird nicht interpretiert." in content
    assert "[Wert aus Tool]" not in content


def test_diagnostic_action_response_includes_status_and_next_action(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    registry = _diagnostic_registry(
        soc=10,
        ha={"critical_count": 0, "warning_count": 0, "informational_count": 0, "critical": [], "warning": [], "informational": []},
        eco_warnings=[],
    )
    pending_action_store.create_action(
        {
            "title": "Diagnosebericht erstellen",
            "description": "test",
            "tool_name": "hauscheck_diagnostic_report",
            "arguments": {},
            "risk": "GREEN",
            "source": "hauscheck",
        }
    )

    result = AssistantOrchestrator(registry=registry).handle_message("Diagnosebericht erstellen")

    assert "Diagnosebericht wurde erstellt:" in result["answer"]
    assert "Status: KRITISCH" in result["answer"]
    assert "Grund: EcoFlow-Batterie kritisch niedrig: 10 %." in result["answer"]
    assert "Nächster Schritt: EcoFlow-Batterie prüfen." in result["answer"]
    assert "Ich habe nichts automatisch geschaltet." in result["answer"]


def _diagnostic_registry(soc: float, ha: dict[str, Any], eco_warnings: list[dict[str, Any]]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("home_assistant_get_problems", "ha", ActionRisk.GREEN, lambda: ha)
    registry.register(
        "ecoflow_energy_overview",
        "ecoflow",
        ActionRisk.GREEN,
        lambda: {
            "soc_percent": soc,
            "pv_power_w": 37,
            "smart_meter_w": 7,
            "grid_power_w": -66,
            "battery_power_w": 0,
            "warnings": eco_warnings,
        },
    )
    return registry
