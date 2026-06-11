from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient

from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.tool_registry import ToolRegistry
from app.config import home_assistant_action_allowlist as allowlist_module
from app.main import app
from app.tools.home_assistant_entities import HomeAssistantEntityCatalog


client = TestClient(app)


def test_fetch_all_entities_maps_safe_catalog_entries(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    monkeypatch.setattr(
        "app.tools.home_assistant_entities.requests.get",
        lambda *args, **kwargs: _Response([_ha_state("light.flur", "Flur Licht", icon="mdi:lightbulb")]),
    )

    result = HomeAssistantEntityCatalog().fetch_all_entities()

    entity = result["entities"][0]
    assert entity["entity_id"] == "light.flur"
    assert entity["domain"] == "light"
    assert entity["friendly_name"] == "Flur Licht"
    assert entity["attributes_summary"] == {
        "device_class": None,
        "unit_of_measurement": None,
        "icon": "mdi:lightbulb",
    }
    assert "attributes" not in entity


def test_cache_is_used_when_fresh(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache([_catalog_entity("light.flur", "Flur Licht")])
    monkeypatch.setattr(
        "app.tools.home_assistant_entities.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live fetch should not run")),
    )

    result = catalog.sync_entities(force=False)

    assert result["source"] == "cache"
    assert result["entity_count"] == 1


def test_force_sync_bypasses_cache(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache([_catalog_entity("light.cached", "Cached")])
    monkeypatch.setattr(
        "app.tools.home_assistant_entities.requests.get",
        lambda *args, **kwargs: _Response([_ha_state("light.live", "Live")]),
    )

    result = catalog.sync_entities(force=True)

    assert result["source"] == "live"
    assert result["entities"][0]["entity_id"] == "light.live"


def test_concurrent_sync_calls_share_one_live_fetch(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    monkeypatch.setenv("HA_ENTITY_CACHE_MAX_AGE_SECONDS", "0")
    catalog = HomeAssistantEntityCatalog()
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(time.time())
        time.sleep(0.05)
        return _Response([_ha_state("light.live", "Live")])

    monkeypatch.setattr("app.tools.home_assistant_entities.requests.get", fake_get)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: catalog.sync_entities(force=False), range(2)))

    assert len(calls) == 1
    assert all(result["entity_count"] == 1 for result in results)


def test_sync_within_min_interval_uses_recent_live_cache(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    monkeypatch.setenv("HA_ENTITY_CACHE_MAX_AGE_SECONDS", "0")
    monkeypatch.setenv("HA_ENTITY_SYNC_MIN_INTERVAL_SECONDS", "30")
    catalog = HomeAssistantEntityCatalog()
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(time.time())
        return _Response([_ha_state(f"light.live_{len(calls)}", "Live")])

    monkeypatch.setattr("app.tools.home_assistant_entities.requests.get", fake_get)

    first = catalog.sync_entities(force=False)
    second = catalog.sync_entities(force=False)

    assert len(calls) == 1
    assert first["source"] == "live"
    assert second["source"] == "cache_recent_live_sync"


def test_unavailable_home_assistant_returns_cache_with_warning(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache([_catalog_entity("light.flur", "Flur Licht")])
    monkeypatch.setattr(
        "app.tools.home_assistant_entities.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = catalog.sync_entities(force=True)

    assert result["source"] == "cache"
    assert result["warning"] == "Home Assistant nicht erreichbar. Ich nutze den letzten lokalen Entity-Cache."


def test_search_entities_finds_flur(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache([_catalog_entity("light.flur", "Flur Licht"), _catalog_entity("sensor.temp", "Temperatur")])

    result = catalog.search_entities("Flur")

    assert result["count"] == 1
    assert result["entities"][0]["entity_id"] == "light.flur"


def test_list_entities_domain_light_returns_only_lights(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache([_catalog_entity("light.flur", "Flur Licht"), _catalog_entity("switch.tv", "TV")])

    result = catalog.list_entities(domain="light")

    assert [entity["entity_id"] for entity in result["entities"]] == ["light.flur"]


def test_list_actionable_candidates_excludes_blocked_domains_and_warns_for_switch(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    catalog = HomeAssistantEntityCatalog()
    catalog.save_cache(
        [
            _catalog_entity("light.flur", "Flur Licht"),
            _catalog_entity("switch.steckdose", "Steckdose"),
            _catalog_entity("scene.abend", "Abend"),
            _catalog_entity("lock.tuer", "Tuer"),
        ]
    )

    result = catalog.list_actionable_candidates()

    ids = [entity["entity_id"] for entity in result["entities"]]
    assert ids == ["light.flur", "scene.abend", "switch.steckdose"]
    assert "lock.tuer" not in ids
    switch = result["entities"][2]
    assert "Switches" in switch["warning"]


def test_allowlisted_entity_is_marked(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path, allowlisted=True)
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret-token")
    monkeypatch.setattr(
        "app.tools.home_assistant_entities.requests.get",
        lambda *args, **kwargs: _Response([_ha_state("light.flur", "Flur Licht")]),
    )

    result = HomeAssistantEntityCatalog().fetch_all_entities()

    assert result["entities"][0]["is_allowlisted"] is True
    assert result["entities"][0]["allowed_actions"] == ["turn_on", "turn_off"]


def test_entity_catalog_status_endpoint_returns_200(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)

    response = client.get("/assistant/home-assistant/entities/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_entity_catalog_search_endpoint_returns_200(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("light.flur", "Flur Licht")])

    response = client.get("/assistant/home-assistant/entities/search?q=flur")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_zeige_alle_lichter_routes_to_entity_catalog(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("light.flur", "Flur Licht")])
    registry = ToolRegistry()
    calls: list[str] = []
    original_execute = registry.execute_tool

    def tracked_execute(name: str, arguments: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
        calls.append(name)
        return original_execute(name, arguments, confirm)

    registry.execute_tool = tracked_execute  # type: ignore[method-assign]

    result = AssistantOrchestrator(registry=registry).handle_message("Jarvis, zeige alle Lichter.")

    assert result["tool"] == "home_assistant_list_entities"
    assert calls == ["home_assistant_list_entities"]
    assert "Flur Licht" in result["answer"]


def test_zeige_alle_heizungen_routes_read_only_to_climate_catalog(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("climate.wohnzimmer", "Wohnzimmer Heizung")])
    registry = ToolRegistry()
    calls: list[str] = []
    original_execute = registry.execute_tool

    def tracked_execute(name: str, arguments: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
        calls.append(name)
        return original_execute(name, arguments, confirm)

    registry.execute_tool = tracked_execute  # type: ignore[method-assign]

    result = AssistantOrchestrator(registry=registry).handle_message("Jarvis, zeige alle Heizungen.")

    assert result["tool"] == "home_assistant_list_entities"
    assert calls == ["home_assistant_list_entities"]
    assert result.get("pending_actions") is None
    assert "nicht freigegeben" not in result["answer"]
    assert "Wohnzimmer Heizung" in result["answer"]
    assert "climate.wohnzimmer" in result["answer"]


def test_zeige_alle_thermostate_maps_to_climate(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("climate.bad", "Bad Thermostat")])

    result = AssistantOrchestrator().handle_message("zeige alle Thermostate")

    assert result["tool"] == "home_assistant_list_entities"
    assert result["result"]["entities"][0]["domain"] == "climate"


def test_zeige_alle_smartsteckdosen_maps_to_switch(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("switch.drucker", "Smartsteckdose Drucker")])

    result = AssistantOrchestrator().handle_message("zeige alle Smartsteckdosen")

    assert result["tool"] == "home_assistant_list_entities"
    assert result["result"]["entities"][0]["domain"] == "switch"


def test_climate_listing_without_climate_entities_explains_sensors_are_read_only(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("sensor.wohnzimmer_temperatur", "Wohnzimmer Temperatur")])

    result = AssistantOrchestrator().handle_message("zeige alle Heizungen")

    assert "keine Home-Assistant-Entities vom Typ climate" in result["answer"]
    assert "sensor.wohnzimmer_rechts_temperatur" in result["answer"]
    assert "nur Messwerte" in result["answer"]


def test_wohnzimmer_search_prioritizes_climate_and_mentions_heating_control(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache(
        [
            _catalog_entity("sensor.wohnzimmer_temperatur", "Wohnzimmer Temperatur"),
            _catalog_entity("binary_sensor.wohnzimmer_fenster", "Wohnzimmer Fenster"),
            _catalog_entity("climate.wohnzimmer", "Wohnzimmer Heizung"),
            _catalog_entity("remote.wohnzimmertv", "Wohnzimmer TV Remote"),
        ]
    )

    result = AssistantOrchestrator().handle_message("Jarvis, suche Wohnzimmer in Home Assistant.")

    assert result["tool"] == "home_assistant_search_entities"
    answer = result["answer"]
    assert answer.index("climate.wohnzimmer") < answer.index("sensor.wohnzimmer_temperatur")
    assert "Für Heizungssteuerung sind nur climate.* Entities relevant." in answer


def test_welche_geraete_kann_ich_freigeben_routes_to_catalog_candidates(monkeypatch, tmp_path: Path) -> None:
    _configure_catalog(monkeypatch, tmp_path)
    HomeAssistantEntityCatalog().save_cache([_catalog_entity("light.flur", "Flur Licht")])

    result = AssistantOrchestrator().handle_message("Welche Geräte kann ich freigeben?")

    assert result["tool"] == "home_assistant_list_actionable_candidates"
    assert "Potentiell freigebbare Kandidaten" in result["answer"]


def _configure_catalog(monkeypatch, tmp_path: Path, allowlisted: bool = False) -> None:
    cache_file = tmp_path / "entities_cache.json"
    allowlist_file = tmp_path / "allowlist.json"
    allowlist = {
        "allowed_entities": [
            {
                "entity_id": "light.flur",
                "friendly_name": "Flur Licht",
                "domain": "light",
                "allowed_actions": ["turn_on", "turn_off"],
            }
        ]
        if allowlisted
        else [],
        "allowed_scenes": [],
        "blocked_domains": ["lock", "alarm_control_panel", "cover", "climate", "fan", "valve", "siren", "camera"],
    }
    allowlist_file.write_text(__import__("json").dumps(allowlist), encoding="utf-8")
    monkeypatch.setattr(allowlist_module, "ALLOWLIST_PATH", allowlist_file)
    monkeypatch.setenv("HA_ENTITY_SYNC_ENABLED", "true")
    monkeypatch.setenv("HA_ENTITY_CACHE_FILE", str(cache_file))
    monkeypatch.setenv("HA_ENTITY_CACHE_MAX_AGE_SECONDS", "900")


def _ha_state(entity_id: str, friendly_name: str, state: str = "on", icon: str | None = None) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "state": state,
        "last_changed": "2026-06-08T10:00:00+00:00",
        "last_updated": "2026-06-08T10:00:00+00:00",
        "attributes": {
            "friendly_name": friendly_name,
            "icon": icon,
            "unit_of_measurement": None,
            "device_class": None,
            "secret": "must-not-be-cached",
        },
    }


def _catalog_entity(entity_id: str, friendly_name: str, state: str = "on") -> dict[str, Any]:
    domain = entity_id.split(".", 1)[0]
    return {
        "entity_id": entity_id,
        "domain": domain,
        "state": state,
        "friendly_name": friendly_name,
        "last_changed": "2026-06-08T10:00:00+00:00",
        "last_updated": "2026-06-08T10:00:00+00:00",
        "attributes_summary": {"device_class": None, "unit_of_measurement": None, "icon": None},
        "is_unavailable": state == "unavailable",
        "is_unknown": state == "unknown",
        "is_actionable_candidate": domain in {"light", "switch", "scene"},
        "is_allowlisted": False,
    }


class _Response:
    def __init__(self, payload: list[dict[str, Any]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, Any]]:
        return self._payload
