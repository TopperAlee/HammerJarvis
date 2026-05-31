from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_returns_status() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "Hammer Jarvis laeuft",
        "version": "0.1",
        "mode": "local-windows",
    }


def test_dashboard_returns_html() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Hammer Jarvis" in response.text


def test_chat_fallback() -> None:
    response = client.post("/chat", json={"message": "Was kannst du heute tun?"})

    assert response.status_code == 200
    assert response.json()["message"] == (
        "Ich habe dich verstanden, aber fuer diesen Befehl gibt es in v0.1 noch kein Werkzeug."
    )


def test_chat_detects_unavailable_intent(monkeypatch) -> None:
    def fake_unavailable(self):
        return [{"entity_id": "sensor.offline", "state": "unavailable"}]

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_unavailable_entities",
        fake_unavailable,
    )

    response = client.post(
        "/chat", json={"message": "Welche Geraete sind nicht verfuegbar?"}
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_unavailable"
    assert response.json()["entities"][0]["entity_id"] == "sensor.offline"


def test_chat_detects_search_intent(monkeypatch) -> None:
    def fake_search(self, query: str):
        return [{"entity_id": "sensor.ecoflow", "query": query}]

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.search_entities",
        fake_search,
    )

    response = client.post("/chat", json={"message": "Suche EcoFlow"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_search"
    assert response.json()["query"] == "EcoFlow"


def test_chat_detects_power_intent(monkeypatch) -> None:
    def fake_power(self):
        return [{"entity_id": "sensor.power", "state": "42"}]

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_power_entities",
        fake_power,
    )

    response = client.post("/chat", json={"message": "Zeige Stromverbrauch"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_power"
    assert response.json()["entities"][0]["entity_id"] == "sensor.power"


def test_chat_detects_problem_diagnostics_intent(monkeypatch) -> None:
    problem_result = {
        "critical_count": 1,
        "warning_count": 0,
        "informational_count": 0,
        "critical": [{"entity_id": "sensor.offline", "state": "unavailable"}],
        "warning": [],
        "informational": [],
    }

    def fake_problems(self):
        return problem_result

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_problem_entities",
        fake_problems,
    )

    response = client.post(
        "/chat", json={"message": "Welche Geraete haben Probleme?"}
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_problems"
    assert response.json()["problems"] == problem_result


def test_chat_detects_ecoflow_diagnostics_intent(monkeypatch) -> None:
    diagnostic = {
        "total": 2,
        "available_count": 1,
        "unavailable_count": 1,
        "unknown_count": 0,
        "power_entities": [],
        "battery_entities": [],
        "problem_entities": [
            {
                "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
                "state": "unavailable",
            }
        ],
        "summary": (
            "Ich habe 2 EcoFlow-Entities gefunden. 1 sind verfuegbar, "
            "1 sind problematisch. Kritisch ist aktuell "
            "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro."
        ),
    }

    def fake_diagnose(self):
        return diagnostic

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.diagnose_ecoflow",
        fake_diagnose,
    )

    response = client.post("/chat", json={"message": "EcoFlow Diagnose"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_ecoflow"
    assert response.json()["message"] == diagnostic["summary"]
    assert response.json()["diagnostic"] == diagnostic


def test_ha_problems_endpoint_returns_classified_counts(monkeypatch) -> None:
    problem_result = {
        "critical_count": 0,
        "warning_count": 1,
        "informational_count": 1,
        "critical": [],
        "warning": [{"entity_id": "sensor.power", "state": "unknown"}],
        "informational": [{"entity_id": "button.restart", "state": "unknown"}],
    }

    def fake_problems(self):
        return problem_result

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_problem_entities",
        fake_problems,
    )

    response = client.get("/ha/problems")

    assert response.status_code == 200
    assert response.json() == problem_result


def test_ha_ecoflow_endpoint_returns_diagnostic(monkeypatch) -> None:
    diagnostic = {
        "total": 1,
        "available_count": 0,
        "unavailable_count": 1,
        "unknown_count": 0,
        "power_entities": [],
        "battery_entities": [],
        "problem_entities": [{"entity_id": "sensor.ecoflow", "state": "unavailable"}],
        "summary": "Ich habe 1 EcoFlow-Entities gefunden.",
    }

    def fake_diagnose(self):
        return diagnostic

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.diagnose_ecoflow",
        fake_diagnose,
    )

    response = client.get("/ha/ecoflow")

    assert response.status_code == 200
    assert response.json() == diagnostic


def test_chat_detects_ecoflow_energy_intent(monkeypatch) -> None:
    overview = {
        "pv_power_w": 493.0,
        "grid_power_w": -453.0,
        "smart_meter_w": 107.0,
        "battery_power_w": 453.0,
        "soc_percent": 33.0,
        "consumption_today_wh": None,
        "grid_import_today_wh": None,
        "battery_energy_today_wh": None,
        "solar_energy_today_wh": None,
        "summary": (
            "Aktuell erzeugt EcoFlow 493 W PV-Leistung. "
            "Die Batterie hat 33 %. Der Smart Meter meldet 107 W."
        ),
        "human_status": {
            "overall": "warning",
            "headline": "EcoFlow laeuft, aber einige Tageswerte sind veraltet.",
            "details": [
                "Batterie: 33 %",
                "PV-Leistung: 493 W",
                "LAN Smart Meter: 107 W",
            ],
        },
    }

    def fake_overview(self):
        return overview

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_ecoflow_energy_overview",
        fake_overview,
    )

    response = client.post("/chat", json={"message": "EcoFlow Energie"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_ecoflow_energy"
    assert response.json()["message"] == (
        "EcoFlow laeuft, aber einige Tageswerte sind veraltet.\n"
        "- Batterie: 33 %\n"
        "- PV-Leistung: 493 W\n"
        "- LAN Smart Meter: 107 W"
    )
    assert response.json()["overview"] == overview


def test_chat_voice_prefix_triggers_ecoflow_energy_intent(monkeypatch) -> None:
    overview = {
        "pv_power_w": 0.0,
        "grid_power_w": None,
        "smart_meter_w": 22.0,
        "battery_power_w": None,
        "soc_percent": 30.0,
        "human_status": {
            "headline": "EcoFlow laeuft, aber einige Werte sind veraltet.",
            "details": ["Batterie: 30 %", "PV-Leistung: 0 W", "LAN Smart Meter: 22 W"],
        },
        "warnings": [
            {"message": "Der Tageswert Solarenergie heute ist veraltet."},
            {"message": "Der Tageswert Verbrauch heute ist veraltet."},
            {"message": "Der Tageswert Netzbezug heute ist veraltet."},
            {"message": "Weitere Warnung."},
        ],
    }

    def fake_overview(self):
        return overview

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_ecoflow_energy_overview",
        fake_overview,
    )

    response = client.post(
        "/chat", json={"message": "Jarvis, was macht EcoFlow gerade?"}
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_ecoflow_energy"
    assert response.json()["message"] == (
        "EcoFlow laeuft, aber einige Werte sind veraltet.\n"
        "- Batterie: 30 %\n"
        "- PV-Leistung: 0 W\n"
        "- LAN Smart Meter: 22 W\n"
        "Hinweise:\n"
        "- Der Tageswert Solarenergie heute ist veraltet.\n"
        "- Der Tageswert Verbrauch heute ist veraltet.\n"
        "- Der Tageswert Netzbezug heute ist veraltet."
    )


def test_chat_battery_question_triggers_ecoflow_energy_intent(monkeypatch) -> None:
    overview = {
        "pv_power_w": None,
        "grid_power_w": None,
        "smart_meter_w": None,
        "battery_power_w": None,
        "soc_percent": 88.0,
        "human_status": {
            "headline": "EcoFlow laeuft ohne erkennbare Warnungen.",
            "details": ["Batterie: 88 %"],
        },
        "warnings": [],
    }

    def fake_overview(self):
        return overview

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_ecoflow_energy_overview",
        fake_overview,
    )

    response = client.post("/chat", json={"message": "Wie voll ist die Batterie?"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ha_ecoflow_energy"


def test_ha_ecoflow_energy_endpoint_returns_overview(monkeypatch) -> None:
    overview = {
        "pv_power_w": None,
        "grid_power_w": None,
        "smart_meter_w": 107.0,
        "battery_power_w": None,
        "soc_percent": None,
        "consumption_today_wh": None,
        "grid_import_today_wh": None,
        "battery_energy_today_wh": None,
        "solar_energy_today_wh": None,
        "summary": "Der Smart Meter meldet 107 W.",
    }

    def fake_overview(self):
        return overview

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.get_ecoflow_energy_overview",
        fake_overview,
    )

    response = client.get("/ha/ecoflow/energy")

    assert response.status_code == 200
    assert response.json() == overview


def test_turn_on_without_confirm_does_not_execute(monkeypatch) -> None:
    called = False

    def fake_turn_on(self, entity_id: str):
        nonlocal called
        called = True
        return {"entity_id": entity_id}

    monkeypatch.setattr(
        "app.tools.home_assistant.HomeAssistantTool.turn_on",
        fake_turn_on,
    )

    response = client.post(
        "/ha/turn-on", json={"entity_id": "light.example", "confirm": False}
    )

    assert response.status_code == 200
    assert response.json()["confirmation_required"] is True
    assert response.json()["risk"] == "YELLOW"
    assert called is False
