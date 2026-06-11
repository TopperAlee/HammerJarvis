import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.agent.permissions import ActionRisk
from app.assistant.actions.pending_action_store import pending_action_store
from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.tool_registry import ToolRegistry
from app.config import home_assistant_action_allowlist as allowlist_module
from app.main import app
from app.tools.home_assistant_actions import HomeAssistantActionTool


client = TestClient(app)


def setup_function() -> None:
    pending_action_store.clear()


def test_missing_allowlist_blocks_all_actions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(allowlist_module, "ALLOWLIST_PATH", tmp_path / "missing.json")

    assert allowlist_module.load_home_assistant_action_allowlist()["allowed_entities"] == []
    assert allowlist_module.is_entity_action_allowed("light.wohnzimmer", "turn_on") is False


def test_allowlisted_light_turn_on_creates_yellow_pending_action(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = AssistantOrchestrator().handle_message("Schalte Wohnzimmer Licht ein")

    assert result["tool"] == "home_assistant_prepare_action"
    assert "Bestätigung" in result["answer"]
    actions = pending_action_store.list_pending_actions()
    assert len(actions) == 1
    assert actions[0]["risk"] == "YELLOW"
    assert actions[0]["requires_confirmation"] is True
    assert actions[0]["tool_name"] == "home_assistant_execute_action"
    assert actions[0]["arguments"] == {"entity_id": "light.wohnzimmer", "action": "turn_on"}


def test_non_allowlisted_entity_is_blocked(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = HomeAssistantActionTool().prepare_home_assistant_action("Küche Licht", "turn_on")

    assert result["blocked"] is True
    assert result["reason"] == "entity_not_allowlisted"


def test_blocked_domain_lock_is_blocked_even_if_configured(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(
        tmp_path,
        monkeypatch,
        entities=[
            {
                "entity_id": "lock.haustuer",
                "friendly_name": "Haustür",
                "domain": "lock",
                "allowed_actions": ["turn_on"],
            }
        ],
    )

    result = HomeAssistantActionTool().prepare_home_assistant_action("Haustür", "turn_on")

    assert result["blocked"] is True
    assert result["reason"] == "entity_not_allowlisted"


def test_execute_action_requires_confirmation(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = ToolRegistry().execute_tool(
        "home_assistant_execute_action",
        {"entity_id": "light.wohnzimmer", "action": "turn_on"},
        confirm=False,
    )

    assert result["confirmation_required"] is True
    assert result["risk"] == ActionRisk.YELLOW


def test_confirmed_yellow_action_calls_home_assistant_service(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    posted: dict[str, Any] = {}

    class Response:
        content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {}

    def fake_post(url, headers, json, timeout):
        posted["url"] = url
        posted["headers"] = headers
        posted["json"] = json
        posted["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.tools.home_assistant_actions.requests.post", fake_post)

    result = ToolRegistry().execute_tool(
        "home_assistant_execute_action",
        {"entity_id": "light.wohnzimmer", "action": "turn_on"},
        confirm=True,
    )

    assert result["executed"] is True
    assert result["result"]["executed"] is True
    assert posted["url"] == "http://ha.local/api/services/light/turn_on"
    assert posted["json"] == {"entity_id": "light.wohnzimmer"}
    assert "secret-token" in posted["headers"]["Authorization"]


def test_chat_command_then_confirmation_executes_mocked_service(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")

    class Response:
        content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {}

    monkeypatch.setattr("app.tools.home_assistant_actions.requests.post", lambda *args, **kwargs: Response())

    prepared = AssistantOrchestrator().handle_message("Schalte Wohnzimmer Licht ein")
    executed = AssistantOrchestrator().handle_message("Bestätige Aktion 1")

    assert prepared["pending_actions"][0]["risk"] == "YELLOW"
    assert executed["tool"] == "action_execute"
    assert "Wohnzimmer Licht wurde eingeschaltet." in executed["answer"]


def test_no_arbitrary_service_name_accepted(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = HomeAssistantActionTool().prepare_home_assistant_action("Wohnzimmer Licht", "delete_everything")

    assert result["blocked"] is True
    assert result["reason"] == "action_not_allowed"


def test_action_proposal_writes_audit_log(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr("app.assistant.orchestrator.write_audit_log", lambda event, data: log_file.write_text(f"{event} {data}", encoding="utf-8"))

    AssistantOrchestrator().handle_message("Schalte Wohnzimmer Licht ein")

    assert "assistant_action_proposed" in log_file.read_text(encoding="utf-8")


def test_allowed_home_assistant_actions_endpoint_returns_200(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    response = client.get("/assistant/home-assistant/actions/allowed")

    assert response.status_code == 200
    assert response.json()["allowed_entities"][0]["entity_id"] == "light.wohnzimmer"


def test_list_allowed_actions_tool_returns_provider_count_and_message(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = ToolRegistry().execute_tool("home_assistant_list_allowed_actions", {})

    assert result["risk"] == ActionRisk.GREEN
    payload = result["result"]
    assert payload["provider"] == "home_assistant"
    assert payload["count"] == 1
    assert "1" in payload["message"]


def test_smart_home_allowlist_question_calls_allowlist_tool_not_capabilities(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)
    calls: list[str] = []
    registry = ToolRegistry()
    original_execute = registry.execute_tool

    def tracked_execute(name: str, arguments: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
        calls.append(name)
        return original_execute(name, arguments, confirm)

    registry.execute_tool = tracked_execute  # type: ignore[method-assign]

    result = AssistantOrchestrator(registry=registry).handle_message("Welche Smart-Home-Aktionen sind freigegeben?")

    assert result["tool"] == "home_assistant_list_allowed_actions"
    assert calls == ["home_assistant_list_allowed_actions"]
    assert "assistant_capabilities" not in calls


def test_empty_allowlist_question_returns_empty_message(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])

    result = AssistantOrchestrator().handle_message("Was darfst du schalten?")

    assert "keine Smart-Home-Aktionen freigegeben" in result["answer"]
    assert "Ich schalte deshalb keine Geräte." in result["answer"]
    assert "app/config/home_assistant_action_allowlist.json" in result["answer"]


def test_allowlisted_light_question_formats_entity_actions_and_confirmation(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = AssistantOrchestrator().handle_message("Zeige freigegebene Geräte")

    assert "Freigegebene Smart-Home-Aktionen:" in result["answer"]
    assert "Wohnzimmer Licht" in result["answer"]
    assert "light.wohnzimmer" in result["answer"]
    assert "einschalten" in result["answer"]
    assert "ausschalten" in result["answer"]
    assert "Blockierte Geräteklassen:" in result["answer"]
    assert "Alle Smart-Home-Aktionen benötigen vor der Ausführung eine Bestätigung." in result["answer"]


def test_discover_returns_only_light_switch_scene(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])
    monkeypatch.setattr(
        "app.tools.home_assistant_actions.HomeAssistantTool.get_all_states",
        lambda self: [
            _ha_state("light.wohnzimmer", "Wohnzimmer Licht"),
            _ha_state("switch.steckdose", "Steckdose"),
            _ha_state("scene.abend", "Abend"),
            _ha_state("sensor.temperatur", "Temperatur"),
        ],
    )

    result = HomeAssistantActionTool().discover_actionable_entities()

    ids = {item["entity_id"] for item in result["candidates"]}
    assert ids == {"light.wohnzimmer", "switch.steckdose", "scene.abend"}


def test_discover_excludes_blocked_domains(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])
    monkeypatch.setattr(
        "app.tools.home_assistant_actions.HomeAssistantTool.get_all_states",
        lambda self: [_ha_state("lock.haustuer", "Haustür"), _ha_state("camera.einfahrt", "Einfahrt")],
    )

    result = HomeAssistantActionTool().discover_actionable_entities()

    assert result["candidates"] == []
    assert result["blocked_count"] == 2


def test_add_light_to_allowlist_creates_yellow_pending_action(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])
    monkeypatch.setattr(
        "app.tools.home_assistant_actions.HomeAssistantTool.get_all_states",
        lambda self: [_ha_state("light.wohnzimmer", "Wohnzimmer Licht")],
    )

    result = AssistantOrchestrator().handle_message("Gib Wohnzimmer Licht frei")

    assert result["tool"] == "home_assistant_allowlist_prepare"
    action = result["pending_actions"][0]
    assert action["risk"] == "YELLOW"
    assert action["tool_name"] == "home_assistant_add_to_allowlist"
    assert action["arguments"]["entity_id"] == "light.wohnzimmer"


def test_confirm_add_writes_to_allowlist(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])

    result = ToolRegistry().execute_tool(
        "home_assistant_add_to_allowlist",
        {
            "entity_id": "light.wohnzimmer",
            "friendly_name": "Wohnzimmer Licht",
            "domain": "light",
            "allowed_actions": ["turn_on", "turn_off"],
        },
        confirm=True,
    )

    assert result["result"]["added"] is True
    assert allowlist_module.is_entity_action_allowed("light.wohnzimmer", "turn_on") is True


def test_duplicate_add_does_not_duplicate_entity(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    ToolRegistry().execute_tool(
        "home_assistant_add_to_allowlist",
        {
            "entity_id": "light.wohnzimmer",
            "friendly_name": "Wohnzimmer Licht",
            "domain": "light",
            "allowed_actions": ["turn_on", "turn_off"],
        },
        confirm=True,
    )

    entities = allowlist_module.list_allowed_entities()
    assert [item["entity_id"] for item in entities].count("light.wohnzimmer") == 1


def test_remove_entity_creates_yellow_pending_action(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = AssistantOrchestrator().handle_message("Entferne Wohnzimmer Licht aus der Freigabe")

    assert result["tool"] == "home_assistant_allowlist_prepare"
    action = result["pending_actions"][0]
    assert action["risk"] == "YELLOW"
    assert action["tool_name"] == "home_assistant_remove_from_allowlist"
    assert action["arguments"]["entity_id"] == "light.wohnzimmer"


def test_confirm_remove_deletes_entity(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch)

    result = ToolRegistry().execute_tool(
        "home_assistant_remove_from_allowlist",
        {"entity_id": "light.wohnzimmer"},
        confirm=True,
    )

    assert result["result"]["removed"] is True
    assert allowlist_module.is_entity_action_allowed("light.wohnzimmer", "turn_on") is False


def test_blocked_domain_cannot_be_allowlisted(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])

    result = ToolRegistry().execute_tool(
        "home_assistant_add_to_allowlist",
        {"entity_id": "lock.haustuer", "friendly_name": "Haustür", "domain": "lock", "allowed_actions": ["turn_on"]},
        confirm=True,
    )

    assert result["result"]["blocked"] is True
    assert result["result"]["reason"] == "domain_not_allowed"


def test_show_actionable_devices_routes_to_discovery(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])
    monkeypatch.setattr(
        "app.tools.home_assistant_actions.HomeAssistantTool.get_all_states",
        lambda self: [_ha_state("light.wohnzimmer", "Wohnzimmer Licht")],
    )

    result = AssistantOrchestrator().handle_message("Zeige schaltbare Geräte")

    assert result["tool"] == "home_assistant_discover_actionable_entities"
    assert "Schaltbare Kandidaten:" in result["answer"]
    assert "Ich habe nichts freigegeben und nichts geschaltet." in result["answer"]


def test_confirm_add_from_chat_writes_allowlist(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, monkeypatch, entities=[])
    monkeypatch.setattr(
        "app.tools.home_assistant_actions.HomeAssistantTool.get_all_states",
        lambda self: [_ha_state("light.wohnzimmer", "Wohnzimmer Licht")],
    )

    prepared = AssistantOrchestrator().handle_message("Gib Wohnzimmer Licht frei")
    executed = AssistantOrchestrator().handle_message("Bestätige Aktion 1")

    assert prepared["pending_actions"][0]["tool_name"] == "home_assistant_add_to_allowlist"
    assert "wurde zur Smart-Home-Freigabe hinzugefügt" in executed["answer"]
    assert allowlist_module.is_entity_action_allowed("light.wohnzimmer", "turn_on") is True


def _ha_state(entity_id: str, friendly_name: str) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "state": "off",
        "attributes": {"friendly_name": friendly_name},
    }


def _write_allowlist(
    tmp_path: Path,
    monkeypatch,
    entities: list[dict[str, Any]] | None = None,
) -> Path:
    path = tmp_path / "home_assistant_action_allowlist.json"
    path.write_text(
        json.dumps(
            {
                "allowed_entities": entities
                if entities is not None
                else [
                    {
                        "entity_id": "light.wohnzimmer",
                        "friendly_name": "Wohnzimmer Licht",
                        "domain": "light",
                        "allowed_actions": ["turn_on", "turn_off"],
                    }
                ],
                "allowed_scenes": [],
                "blocked_domains": ["lock", "alarm_control_panel", "cover", "climate", "fan", "valve", "siren", "camera"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(allowlist_module, "ALLOWLIST_PATH", path)
    return path
