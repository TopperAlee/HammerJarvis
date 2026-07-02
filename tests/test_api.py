from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app
from app.desktop_agent.event_bridge import desktop_event_bridge


client = TestClient(app)


def reset_desktop_event_bridge() -> None:
    desktop_event_bridge.clients.clear()
    desktop_event_bridge.pending_wake_event = None
    desktop_event_bridge.pending_wake_expires_at = None
    desktop_event_bridge.last_dashboard_heartbeat = None
    desktop_event_bridge.last_wake_event = None


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


def test_dashboard_hud_static_assets_are_present() -> None:
    html_response = client.get("/dashboard")
    css_response = client.get("/static/dashboard.css")
    js_response = client.get("/static/dashboard.js")

    assert html_response.status_code == 200
    assert css_response.status_code == 200
    assert js_response.status_code == 200
    assert "HAMMER JARVIS HUD DASHBOARD v2" in html_response.text
    assert ".jarvis-core" in css_response.text
    assert "initDashboard" in js_response.text


def test_dashboard_speech_voice_selector_assets_are_present() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="voiceSelect"' in html
    assert 'id="voiceSelectStatus"' in html
    assert '"voiceSelect"' in js
    assert '"voiceSelectStatus"' in js
    assert '"voiceLoadingPanel"' in js
    assert '"voiceStatusText"' in js
    assert '"voiceProgressText"' in js
    assert '"voiceDiagnosticText"' in js
    assert "speech-settings" in css
    assert "speechVoiceStorageKey" in js
    assert "startVoiceLoadingCycle" in js
    assert "applyAvailableVoices" in js
    assert "choosePreferredGermanVoice" in js
    assert "populateVoiceSelectFromState" in js
    assert "localStorage.setItem" in js
    assert "localStorage.getItem" in js


def test_dashboard_speech_preparation_and_chunking_are_present() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "prepareSpeechText" in js
    assert "splitSpeechText" in js
    assert "Ein technischer Codeabschnitt wurde ausgelassen." in js
    assert "Link ausgelassen." in js
    assert "targetChunkLength: 220" in js
    assert "maxChunkLength: 260" in js
    assert "speechRunId" in js
    assert "cancelSpeechOutput" in js
    assert "window.speechSynthesis.cancel()" in js


def test_dashboard_speech_voice_loading_is_bounded_and_final() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "window.speechSynthesis.getVoices()" in js
    assert "voiceschanged" in js
    assert "const VOICE_RETRY_DELAYS_MS = [0, 100, 300, 750, 1500, 3000]" in js
    assert "const VOICE_LOAD_WATCHDOG_MS = 5500" in js
    assert "const VOICE_LOAD_STATES = {" in js
    assert 'EMPTY: "empty"' in js
    assert "voiceLoadGeneration" in js
    assert "clearVoiceLoadTimers" in js
    assert "Keine Browser-Stimmen verfügbar" in js
    assert "Keine Stimmen nach 5 Sekunden. Windows-Sprachpakete oder Browser prüfen." in js
    assert "keine deutsche Stimme gefunden" in js
    assert "Sprachausgabe nicht unterstützt" in js
    assert "getValidSpeechVoices" in js
    assert "try {" in js
    assert "console.error(\"[Hammer Jarvis Voice]" in js
    assert "scheduleSpeechVoiceRetries" not in js
    assert "refreshSpeechVoices" not in js


def test_dashboard_activity_panel_assets_are_present() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert '<section id="activityPanel"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'id="activeActivities"' in html
    assert 'id="recentActivities"' in html
    assert 'id="clearActivities"' in html
    assert ".activity-panel" in css
    assert ".activity-spinner" in css
    assert ".button-loading" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "function startActivity" in js
    assert "function updateActivity" in js
    assert "function finishActivity" in js
    assert "function failActivity" in js
    assert "function timeoutActivity" in js
    assert "function cancelActivity" in js
    assert "renderActivities" in js
    assert "withButtonLoading" in js
    assert "Zeitüberschreitung" in js


def test_dashboard_fetches_are_timeout_bounded() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "const fetchTimeoutMs = 15000" in js
    assert "new AbortController()" in js
    assert "controller.abort(\"timeout\")" in js
    assert "timeoutMs" in js
    assert "timeoutError.kind = \"timeout\"" in js
    assert "Dashboard wird aktualisiert" in js
    assert "0 von" in js


def test_dashboard_voice_reload_and_retry_progress_are_present() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="reloadVoices"' in html
    assert 'id="voiceLoadingIndicator"' in html
    assert 'id="voiceStatusText"' in html
    assert 'id="voiceProgressText"' in html
    assert 'id="voiceDiagnosticText"' in html
    assert 'aria-busy="false"' in html
    assert 'role="status"' in html
    assert "reloadSpeechVoices" in js
    assert "VOICE_RETRY_DELAYS_MS.length" in js
    assert "Versuch ${attempt} von" in js
    assert "läuft seit" in js
    assert "Keine Stimmen nach 5 Sekunden" in js
    assert "Windows-Sprachpakete oder Browser prüfen" in js
    assert "Spracherkennung läuft" in js
    assert "Jarvis spricht" in js


def test_dashboard_voice_loading_state_machine_assets_are_present() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "VOICE_LOAD_STATES" in js
    for state in ["idle", "loading", "success", "empty", "unsupported", "error", "cancelled"]:
        assert state in js
    assert "voiceLoadState" in js
    assert "voiceLoadAttempt" in js
    assert "voiceLoadStartTime" in js
    assert "voiceLoadTimers" in js
    assert "voiceLoadElapsedTimer" in js
    assert "voiceLoadInProgress" in js
    assert "generation !== voiceLoadGeneration" in js
    assert "VOICE_LOAD_WATCHDOG_MS" in js
    assert "clearVoiceLoadTimers" in js
    assert ".voice-loading-spinner" in css
    assert "@keyframes voiceSpin" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "TTS API:" in html
    assert "getVoices():" in html


def test_dashboard_voice_init_order_is_deterministic() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    init_body = js[js.index("function initDashboard()") :]

    assert init_body.index("bindElements();") < init_body.index("wireEvents();")
    assert init_body.index("wireEvents();") < init_body.index("initializeVoiceSubsystemSafely();")
    assert init_body.index("initializeVoiceSubsystemSafely();") < init_body.index("initializeRemainingDashboardSafely();")
    assert "function initializeVoiceSubsystemSafely()" in js
    assert "startVoiceLoadingCycle();" in js
    assert "function initializeRemainingDashboardSafely()" in js
    assert "refreshDashboard();" in js[js.index("function initializeRemainingDashboardSafely()") :]


def test_dashboard_bootstrap_handles_loaded_and_loading_dom() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "function bootstrapDashboard()" in js
    assert "let dashboardInitialized = false" in js
    assert "if (dashboardInitialized)" in js
    assert "dashboardInitialized = true" in js
    assert 'document.readyState === "loading"' in js
    assert 'document.addEventListener("DOMContentLoaded", bootstrapDashboard, { once: true })' in js
    assert "bootstrapDashboard();" in js
    assert 'document.addEventListener("DOMContentLoaded", initDashboard)' not in js


def test_dashboard_voice_bootstrap_is_isolated_and_visible() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "function initializeVoiceSubsystemSafely()" in js
    assert "renderVoiceInitializationError" in js
    assert "validateVoiceDomElements" in js
    assert "requiredVoiceElementIds" in js
    assert "Bootstrap beendet, aber Zustand blieb idle" in js
    assert "Fehlende Voice-DOM-Elemente" in js
    assert "function reloadSpeechVoices()" in js
    assert "startVoiceLoadingCycle();" in js
    assert "wireDashboardEvents" in js


def test_dashboard_build_marker_and_cache_busting_are_present() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'src="/static/dashboard.js?v=topbar-navigation-20260702" defer' in html
    assert 'const DASHBOARD_BUILD = "topbar-navigation-20260702"' in js
    assert "dashboard.js geladen" in js
    assert "document.documentElement.dataset.dashboardBuild = DASHBOARD_BUILD" in js
    assert "Build: ${DASHBOARD_BUILD}" in js


def test_dashboard_top_menu_entries_are_actionable_or_disabled() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert 'class="top-tab active"' in html
    assert 'data-target="commandCenter"' in html
    assert 'data-target="engineering"' in html
    assert 'data-target="knowledge"' in html
    assert 'data-target="haControlCenter"' in html
    assert 'data-target="chat"' in html
    assert 'data-target="performance"' in html
    assert 'href="#"' not in html
    assert "navigateDashboardSection" in js
    assert "setActiveTopTab" in js
    assert "scrollIntoView" in js
    assert 'button.matches(".top-tab:not(:disabled)")' in js
    assert ".top-tab.active" in css


def test_dashboard_global_error_handlers_are_registered() -> None:
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "registerGlobalDashboardErrorHandlers();" in js
    assert 'window.addEventListener("error"' in js
    assert 'window.addEventListener("unhandledrejection"' in js
    assert "Dashboard-Laufzeitfehler" in js
    assert "Unbehandelte Dashboard-Promise" in js


def test_no_node_or_npm_system_was_added() -> None:
    assert not Path("package.json").exists()
    assert not Path("package-lock.json").exists()
    assert not Path("node_modules").exists()


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


def test_wake_word_status_endpoint_returns_safe_defaults() -> None:
    response = client.get("/assistant/voice/wake/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["wake_word"] == "Jarvis"
    assert data["model"] == ""
    assert data["audio_stored"] is False
    assert data["sample_rate"] == 16000
    assert data["frame_ms"] == 80


def test_env_example_has_no_active_hey_jarvis_default() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "WAKE_ENGINE=windows_speech" in content
    assert "WAKE_WORD=Jarvis" in content
    assert "WAKE_CONFIDENCE_THRESHOLD=0.40" in content
    assert "WAKE_RECOGNIZER_CULTURE=auto" in content
    assert "WAKE_ACCEPTED_TRANSCRIPTS=Jarvis,Jervis,Dschawis" in content
    assert "WAKE_WORD_MODEL=hey_jarvis" not in content


def test_setup_wake_word_script_does_not_suggest_hey_jarvis() -> None:
    content = Path("scripts/setup-wake-word.ps1").read_text(encoding="utf-8")

    assert "WAKE_ENGINE=windows_speech" in content
    assert "WAKE_WORD_MODEL_PATH=app/data/models/wake/jarvis.onnx" in content
    assert "WAKE_WORD_MODEL=hey_jarvis" not in content


def test_desktop_agent_scripts_expose_safe_test_modes_and_utf8_status() -> None:
    listener = Path("scripts/jarvis-wake-listener.ps1").read_text(encoding="utf-8")
    speech = Path("scripts/speak-local.ps1").read_text(encoding="utf-8")
    status = Path("scripts/status-desktop-agent.ps1").read_text(encoding="utf-8")
    calibration = Path("scripts/test-jarvis-wake.ps1").read_text(encoding="utf-8")

    assert "[switch]$TestEmitReady" in listener
    assert "[switch]$Diagnostics" in listener
    assert "[switch]$ShowRecognizedText" in listener
    assert "[int]$ProbeSeconds" in listener
    assert "RecognizeAsync" not in listener
    assert "add_SpeechRecognized" not in listener
    assert "add_AudioStateChanged" not in listener
    assert "$engine.Recognize(" in listener
    assert "[TimeSpan]::FromMilliseconds(750)" in listener
    assert "$ProbeSeconds -gt 0" in listener
    assert 'type = "ready"' in listener
    assert 'type = "diagnostic_summary"' in listener
    assert "-Completed $true" in listener
    assert "-Completed $false" in listener
    assert "wake_word = \"Jarvis\"" in listener
    assert '"hey jarvis"' in listener.lower()
    assert 'word = "Jarvis"' in listener
    assert "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)" in listener
    assert "[Console]::Error.WriteLine" in listener
    assert "[switch]$ValidateOnly" in speech
    assert "Invoke-Expression" not in speech
    assert "Get-Content -Encoding UTF8" in status
    assert "Schwellwert:" in status
    assert "Sagen Sie jetzt mehrmals deutlich: Jarvis" in calibration
    assert "-RecognizerCulture" in calibration
    assert "diagnostic_summary" in calibration
    assert "$process.ExitCode" in calibration
    assert "$summaryCount -ne 1" in calibration


def test_readme_only_mentions_hey_jarvis_as_non_default_explanation() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "WAKE_WORD_MODEL=hey_jarvis" not in content
    assert "nicht stillschweigend als Ersatz" in content


def test_dashboard_contains_hands_free_voice_controls() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    html = response.text
    assert '<meta charset="UTF-8">' in html
    assert 'id="handsFreeToggle"' in html
    assert 'id="desktopAgentStatus"' in html
    assert "Wake Word:" in html
    assert ">Jarvis<" in html
    assert "Audiodaten werden nicht gespeichert" in html
    assert "Hey Jarvis" not in html


def test_wake_word_audio_worklet_is_served() -> None:
    response = client.get("/static/audio/wake-word-processor.js")

    assert response.status_code == 200
    assert "registerProcessor(\"wake-word-processor\"" in response.text


def test_dashboard_js_has_hands_free_state_machine() -> None:
    response = client.get("/static/dashboard.js")

    assert response.status_code == 200
    js = response.text
    assert "HANDS_FREE_STATES" in js
    assert "/assistant/voice/wake/stream" in js
    assert "getUserMedia" in js
    assert "playWakeBeep" in js
    assert "startCommandRecognition" in js
    assert "Verbindung zur lokalen Weckwort-Erkennung" in js


def test_assistant_health_endpoint_returns_ready() -> None:
    response = client.get("/assistant/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_desktop_status_endpoint_returns_bridge_status() -> None:
    reset_desktop_event_bridge()
    response = client.get("/assistant/desktop/status")

    assert response.status_code == 200
    data = response.json()
    assert data["dashboard_clients"] >= 0
    assert data["wake_word"] == "Jarvis"
    assert data["audio_stored"] is False
    for key in [
        "agent_state",
        "backend_ready",
        "event_bridge_ready",
        "wake_listener_ready",
        "wake_listener_alive",
        "wake_listener_pid",
        "wake_audio_ready",
        "wake_audio_state",
        "wake_last_audio_level",
        "wake_last_audio_at",
        "wake_last_speech_detected_at",
        "wake_last_rejected_confidence",
        "wake_engine",
        "wake_culture",
        "wake_recognizer",
        "wake_threshold",
        "wake_ready_at",
        "last_wake_detection_at",
        "ready_announcement_enabled",
        "ready_announcement_attempted",
        "ready_announcement_succeeded",
        "ready_announcement_error",
        "agent_python",
        "backend_python",
        "project_root",
        "websocket_transport",
        "backend_pid",
    ]:
        assert key in data
    serialized = str(data).lower()
    assert "token" not in serialized
    assert "secret" not in serialized


def test_desktop_wake_endpoint_returns_without_dashboard_client() -> None:
    reset_desktop_event_bridge()
    response = client.post(
        "/assistant/desktop/wake",
        json={"wake_word": "Jarvis", "source": "desktop_agent", "confidence": 0.9},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["event"]["wake_word"] == "Jarvis"
    assert data["sent"] == 0


def test_desktop_event_websocket_accepts_client_and_counts_disconnect() -> None:
    reset_desktop_event_bridge()

    with client.websocket_connect("/assistant/desktop/events", headers={"origin": "http://testserver"}) as websocket:
        status = websocket.receive_json()
        assert status["type"] == "desktop_status"
        assert client.get("/assistant/desktop/status").json()["dashboard_clients"] == 1

    assert client.get("/assistant/desktop/status").json()["dashboard_clients"] == 0


def test_desktop_event_websocket_accepts_same_origin_non_8001_port() -> None:
    reset_desktop_event_bridge()

    with client.websocket_connect(
        "/assistant/desktop/events",
        headers={"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:8000"},
    ) as websocket:
        status = websocket.receive_json()
        assert status["type"] == "desktop_status"
        assert client.get("/assistant/desktop/status").json()["dashboard_clients"] == 1


def test_desktop_wake_event_is_sent_to_connected_client() -> None:
    reset_desktop_event_bridge()

    with client.websocket_connect("/assistant/desktop/events", headers={"origin": "http://testserver"}) as websocket:
        websocket.receive_json()
        response = client.post(
            "/assistant/desktop/wake",
            json={"wake_word": "Jarvis", "source": "desktop_agent", "confidence": 0.475},
        )
        assert response.status_code == 200
        assert response.json()["sent"] == 1
        event = websocket.receive_json()
        assert event["type"] == "wake_detected"
        assert event["wake_word"] == "Jarvis"
        assert event["source"] == "desktop_agent"
        assert event["confidence"] == 0.475


def test_pending_wake_event_is_delivered_once_to_later_client() -> None:
    reset_desktop_event_bridge()

    response = client.post(
        "/assistant/desktop/wake",
        json={"wake_word": "Jarvis", "source": "desktop_agent", "confidence": 0.5},
    )
    assert response.status_code == 200
    assert response.json()["sent"] == 0
    assert client.get("/assistant/desktop/status").json()["pending_wake_event"] is True

    with client.websocket_connect("/assistant/desktop/events", headers={"origin": "http://testserver"}) as websocket:
        event = websocket.receive_json()
        assert event["type"] == "wake_detected"
        assert event["wake_word"] == "Jarvis"
        status = websocket.receive_json()
        assert status["type"] == "desktop_status"
        assert status["pending_wake_event"] is False

    assert client.get("/assistant/desktop/status").json()["pending_wake_event"] is False


def test_dashboard_desktop_event_bridge_assets_are_present() -> None:
    js = client.get("/static/dashboard.js").text

    assert "/assistant/desktop/events" in js
    assert "DESKTOP_EVENT_RECONNECT_DELAYS_MS = [1000, 2000, 5000]" in js
    assert "handleDesktopEvent" in js
    assert "startCommandRecognition({" in js
    assert "source: \"desktop_agent\"" in js
    assert "elements.voiceButton.addEventListener(\"click\", () => withButtonLoading(elements.voiceButton, \"Hört zu...\", startVoiceRecognition))" not in js
def test_dashboard_desktop_event_bridge_uses_same_origin_websocket_and_guards_recognition() -> None:
    js = client.get("/static/dashboard.js").text

    assert "function buildDesktopEventSocketUrl" in js
    assert 'locationSource.protocol === "https:" ? "wss:" : "ws:"' in js
    assert "`${protocol}//${locationSource.host}/assistant/desktop/events`" in js
    assert "new WebSocket(buildDesktopEventSocketUrl())" in js
    assert "window.HammerJarvisDashboard" in js
    assert "HANDS_FREE_STATES.COMMAND_LISTENING" in js
    assert "HANDS_FREE_STATES.PROCESSING" in js
    assert "HANDS_FREE_STATES.SPEAKING" in js
    assert "elements.voiceButton.addEventListener(\"click\", () => startCommandRecognition({ source: \"button\", autoSend: true }))" in js
