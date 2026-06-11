import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.assistant.actions.action_executor import ActionExecutor
from app.assistant.actions.pending_action_store import pending_action_store
from app.assistant.orchestrator import AssistantOrchestrator
from app.config import home_assistant_control_policy as policy_module
from app.main import app
from app.tools.home_assistant_control_broker import HomeAssistantControlBroker
from app.tools.home_assistant_entities import HomeAssistantEntityCatalog


client = TestClient(app)


def setup_function() -> None:
    pending_action_store.clear()


def test_light_turn_on_prepares_yellow_action(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_control_action("light.flur", "turn_on")

    assert result["prepared"] is True
    assert result["risk"] == "YELLOW"
    assert result["requires_confirmation"] is True


def test_switch_hall_override_resolves_flur_licht(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().resolve_control_intent("Flur Licht einschalten")

    assert result["resolved"] is True
    assert result["entity_id"] == "switch.hall"
    assert result["action"] == "turn_on"


def test_non_configured_switch_prepares_with_warning(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_control_action("switch.drucker", "turn_off")

    assert result["prepared"] is True
    assert result["risk"] == "YELLOW"
    assert "Switches" in result["warning"]


def test_lock_alarm_and_camera_are_blocked_by_default(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    broker = HomeAssistantControlBroker()

    assert broker.prepare_control_action("lock.front", "turn_on")["blocked"] is True
    assert broker.prepare_control_action("alarm_control_panel.home", "turn_on")["blocked"] is True
    assert broker.prepare_control_action("camera.door", "turn_on")["blocked"] is True


def test_arbitrary_service_name_is_rejected(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_control_action("light.flur", "delete_everything")

    assert result["blocked"] is True
    assert result["reason"] == "action_not_supported"


def test_climate_set_temperature_prepares_orange_action(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_control_action(
        "climate.wohnzimmer",
        "set_temperature",
        {"temperature": 21},
    )

    assert result["prepared"] is True
    assert result["risk"] == "ORANGE"
    assert "Klima" in result["warning"]


def test_cover_close_prepares_orange_action(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_control_action("cover.rollladen", "close_cover")

    assert result["prepared"] is True
    assert result["risk"] == "ORANGE"
    assert "mechanische Bewegung" in result["warning"]


def test_batch_all_lights_off_includes_only_lights(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = HomeAssistantControlBroker().prepare_batch_action(domain="light", action="turn_off")

    ids = [item["entity_id"] for item in result["actions"]]
    assert ids == ["light.flur", "light.kueche"]
    assert "switch.drucker" not in ids


def test_batch_excludes_blocked_entities(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, blocked_entities=["light.kueche"])

    result = HomeAssistantControlBroker().prepare_batch_action(domain="light", action="turn_off")

    assert [item["entity_id"] for item in result["actions"]] == ["light.flur"]
    assert result["excluded"][0]["entity_id"] == "light.kueche"


def test_yellow_action_requires_confirmation(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    result = AssistantOrchestrator().handle_message("Flur Licht einschalten")
    action_id = result["pending_actions"][0]["id"]

    executed = ActionExecutor().execute(action_id, confirm=False)

    assert executed["confirmation_required"] is True
    assert executed["status"] == "pending"


def test_orange_action_requires_confirmation_and_warning(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Temperatur auf 21 Grad")

    assert result["pending_actions"][0]["risk"] == "ORANGE"
    assert "Warnung" in result["answer"]


def test_red_action_blocked_without_pin(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, enable_high_risk=True)

    result = HomeAssistantControlBroker().prepare_control_action("lock.front", "turn_on")

    assert result["blocked"] is True
    assert result["reason"] in {"domain_disabled", "pin_not_configured", "action_not_supported"}


def test_entity_knowledge_does_not_imply_immediate_execution(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr("app.tools.home_assistant_control_broker.requests.post", lambda *args, **kwargs: calls.append("post"))

    result = AssistantOrchestrator().handle_message("Flur Licht einschalten")

    assert result["tool"] == "home_assistant_prepare_control_action"
    assert result["pending_actions"]
    assert calls == []


def test_confirmed_action_executes_known_mapping(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    posted: dict[str, Any] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {}

    def fake_post(url, headers, json, timeout):
        posted["url"] = url
        posted["headers"] = headers
        posted["json"] = json
        return Response()

    monkeypatch.setattr("app.tools.home_assistant_control_broker.requests.post", fake_post)

    result = HomeAssistantControlBroker().execute_control_action("switch.hall", "turn_on")

    assert result["executed"] is True
    assert posted["url"] == "http://ha.local/api/services/switch/turn_on"
    assert posted["json"] == {"entity_id": "switch.hall"}


def test_trusted_auto_light_executes_without_pending_action(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    posted: list[dict[str, Any]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.tools.home_assistant_control_broker.requests.post",
        lambda url, headers, json, timeout: posted.append({"url": url, "json": json}) or Response(),
    )

    result = AssistantOrchestrator().handle_message("Flur Licht einschalten")

    assert result["tool"] == "home_assistant_execute_control_action"
    assert "Ausgeführt" in result["answer"]
    assert "Auto-Ausführung gemäß Smart-Home-Policy" in result["answer"]
    assert result.get("pending_actions") is None
    assert pending_action_store.list_pending_actions() == []
    assert posted[0]["url"] == "http://ha.local/api/services/switch/turn_on"


def test_trusted_switch_executes_directly(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    posted: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.tools.home_assistant_control_broker.requests.post",
        lambda url, headers, json, timeout: posted.append(json["entity_id"]) or Response(),
    )

    result = AssistantOrchestrator().handle_message("Flur Licht ausschalten")

    assert result["result"]["executed"] is True
    assert posted == ["switch.hall"]


def test_untrusted_switch_does_not_auto_execute(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)

    result = HomeAssistantControlBroker().prepare_control_action("switch.drucker", "turn_off")

    assert result["prepared"] is True
    assert result["auto_execute"] is False
    assert "noch nicht als sichere Smartsteckdose" in result["message"]


def test_climate_temperature_auto_executes_within_range(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    posted: list[dict[str, Any]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.tools.home_assistant_control_broker.requests.post",
        lambda url, headers, json, timeout: posted.append(json) or Response(),
    )

    result = AssistantOrchestrator().handle_message("Wohnzimmer auf 21 Grad")

    assert result["tool"] == "home_assistant_execute_control_action"
    assert "21 °C" in result["answer"]
    assert posted == [{"entity_id": "climate.wohnzimmer", "temperature": 21.0}]


def test_climate_control_uses_only_climate_domain(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    HomeAssistantEntityCatalog().save_cache(
        [
            _entity("sensor.wohnzimmer_temperatur", "Wohnzimmer Temperatur"),
            _entity("climate.wohnzimmer", "Wohnzimmer Heizung"),
        ]
    )

    result = HomeAssistantControlBroker().resolve_control_intent("stelle Wohnzimmer auf 21 Grad")

    assert result["resolved"] is True
    assert result["entity_id"] == "climate.wohnzimmer"
    assert result["action"] == "set_temperature"


def test_climate_control_no_climate_match_rejects_sensor_control(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    HomeAssistantEntityCatalog().save_cache([_entity("sensor.wohnzimmer_temperatur", "Wohnzimmer Temperatur")])

    result = AssistantOrchestrator().handle_message("stelle Wohnzimmer auf 21 Grad")

    assert result["tool"] == "home_assistant_resolve_control_intent"
    assert "keine passende Home-Assistant-Heizungs-Entity" in result["answer"]
    assert "sensor.* Temperaturwerte lesen" in result["answer"]


def test_climate_control_multiple_matches_asks_clarification(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    HomeAssistantEntityCatalog().save_cache(
        [
            _entity("climate.wohnzimmer_rechts", "Wohnzimmer rechts"),
            _entity("climate.wohnzimmer_links", "Wohnzimmer links"),
            _entity("sensor.wohnzimmer_temperatur", "Wohnzimmer Temperatur"),
        ]
    )

    result = AssistantOrchestrator().handle_message("Wohnzimmer auf 21 Grad")

    assert result["tool"] == "home_assistant_resolve_control_intent"
    assert "mehrere passende Heizungen" in result["answer"]
    assert "climate.wohnzimmer_rechts" in result["answer"]
    assert "sensor.wohnzimmer_temperatur" not in result["answer"]


def test_climate_temperature_outside_auto_range_is_blocked(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)

    result = HomeAssistantControlBroker().prepare_control_action("climate.wohnzimmer", "set_temperature", {"temperature": 30})

    assert result["blocked"] is True
    assert "außerhalb der erlaubten Auto-Grenze" in result["message"]


def test_blocked_domains_never_auto_execute(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)
    broker = HomeAssistantControlBroker()

    assert broker.prepare_control_action("lock.front", "turn_on")["blocked"] is True
    assert broker.prepare_control_action("alarm_control_panel.home", "turn_on")["blocked"] is True
    assert broker.prepare_control_action("camera.door", "turn_on")["blocked"] is True
    assert broker.prepare_control_action("button.reset", "turn_on")["blocked"] is True


def test_auto_policy_endpoints(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path, trusted_auto=True)

    policy_response = client.get("/assistant/home-assistant/control/auto-policy")
    switches_response = client.get("/assistant/home-assistant/control/trusted-switches")
    reload_response = client.post("/assistant/home-assistant/control/auto-policy/reload")

    assert policy_response.status_code == 200
    assert policy_response.json()["control_mode"] == "trusted_auto"
    assert switches_response.status_code == 200
    assert switches_response.json()["trusted_switches"][0]["entity_id"] == "switch.hall"
    assert reload_response.status_code == 200


def test_control_policy_endpoint_returns_200(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)

    response = client.get("/assistant/home-assistant/control/policy")

    assert response.status_code == 200
    assert response.json()["control_mode"] == "confirmed"


def _configure(
    monkeypatch,
    tmp_path: Path,
    blocked_entities: list[str] | None = None,
    enable_high_risk: bool = False,
    trusted_auto: bool = False,
) -> None:
    policy = _policy(enable_high_risk=enable_high_risk, blocked_entities=blocked_entities or [], trusted_auto=trusted_auto)
    policy_file = tmp_path / "control_policy.json"
    policy_file.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(policy_module, "POLICY_PATH", policy_file)
    cache_file = tmp_path / "entities_cache.json"
    monkeypatch.setenv("HA_ENTITY_CACHE_FILE", str(cache_file))
    HomeAssistantEntityCatalog().save_cache(
        [
            _entity("light.flur", "Flur Licht"),
            _entity("light.kueche", "Küche Licht"),
            _entity("switch.hall", "Flur Licht"),
            _entity("switch.drucker", "Steckdose Drucker"),
            _entity("climate.wohnzimmer", "Wohnzimmer Heizung"),
            _entity("cover.rollladen", "Rollladen"),
            _entity("lock.front", "Haustür"),
            _entity("alarm_control_panel.home", "Alarm"),
            _entity("camera.door", "Kamera"),
            _entity("button.reset", "Reset Button"),
        ]
    )


def _entity(entity_id: str, friendly_name: str) -> dict[str, Any]:
    domain = entity_id.split(".", 1)[0]
    return {
        "entity_id": entity_id,
        "domain": domain,
        "state": "on",
        "friendly_name": friendly_name,
        "attributes_summary": {},
        "is_actionable_candidate": domain in {"light", "switch", "scene"},
        "is_allowlisted": False,
    }


def _policy(enable_high_risk: bool = False, blocked_entities: list[str] | None = None, trusted_auto: bool = False) -> dict[str, Any]:
    policy = {
        "control_mode": "confirmed",
        "require_confirmation_for_all_actions": True,
        "enable_high_risk_actions": enable_high_risk,
        "require_pin_for_high_risk": True,
        "confirmation_pin_hash": "",
        "default_action_expiry_minutes": 10,
        "blocked_entities": blocked_entities or [],
        "blocked_domains": ["valve", "siren", "remote", "vacuum"],
        "domains": {
            "light": {"enabled": True, "risk": "YELLOW", "allowed_actions": ["turn_on", "turn_off", "toggle"]},
            "switch": {
                "enabled": True,
                "risk": "YELLOW",
                "allowed_actions": ["turn_on", "turn_off", "toggle"],
                "warning": "Switches können Steckdosen oder Geräte schalten. Nur ausführen, wenn der Zweck klar ist.",
            },
            "scene": {"enabled": True, "risk": "YELLOW", "allowed_actions": ["turn_on"]},
            "script": {"enabled": True, "risk": "ORANGE", "allowed_actions": ["turn_on"]},
            "automation": {"enabled": True, "risk": "ORANGE", "allowed_actions": ["turn_on", "turn_off"]},
            "climate": {
                "enabled": True,
                "risk": "ORANGE",
                "allowed_actions": ["set_temperature"],
                "warning": "Klima-/Heizungsänderungen beeinflussen Komfort und Energieverbrauch.",
            },
            "cover": {
                "enabled": True,
                "risk": "ORANGE",
                "allowed_actions": ["open_cover", "close_cover", "stop_cover"],
                "warning": "Abdeckungen/Rollläden können mechanische Bewegung auslösen.",
            },
            "lock": {"enabled": False, "risk": "RED", "allowed_actions": []},
            "alarm_control_panel": {"enabled": False, "risk": "RED", "allowed_actions": []},
            "camera": {"enabled": False, "risk": "RED", "allowed_actions": []},
            "button": {"enabled": False, "risk": "RED", "allowed_actions": []},
        },
        "entity_overrides": {
            "switch.hall": {
                "enabled": True,
                "risk": "YELLOW",
                "friendly_name": "Flur Licht",
                "allowed_actions": ["turn_on", "turn_off"],
                "auto_execute": trusted_auto,
                "category": "light_equivalent",
            }
        },
    }
    if trusted_auto:
        policy.update(
            {
                "control_mode": "trusted_auto",
                "require_confirmation_for_all_actions": False,
                "auto_execute_enabled": True,
                "auto_execute_domains": {
                    "light": {"enabled": True, "actions": ["turn_on", "turn_off", "toggle"], "risk": "YELLOW"},
                    "switch": {
                        "enabled": True,
                        "actions": ["turn_on", "turn_off", "toggle"],
                        "risk": "YELLOW",
                        "only_if_trusted_switch": True,
                    },
                    "climate": {
                        "enabled": True,
                        "actions": ["set_temperature"],
                        "risk": "ORANGE",
                        "temperature_min": 16,
                        "temperature_max": 24,
                        "max_delta_celsius": 3,
                    },
                },
                "require_confirmation_domains": ["cover", "script", "automation"],
                "blocked_domains": ["lock", "alarm_control_panel", "camera", "siren", "valve", "button", "remote", "vacuum"],
                "trusted_switches": [
                    {"entity_id": "switch.hall", "friendly_name": "Flur Licht", "category": "light_equivalent", "auto_execute": True}
                ],
            }
        )
    return policy
