from typing import Any

from fastapi.testclient import TestClient

from app.agent.permissions import ActionRisk
from app.assistant.formatters.ecoflow_formatter import format_ecoflow_energy_answer
from app.assistant.llm_client import sanitize_german_answer, sanitize_identity_response
from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.tool_registry import ToolRegistry
from app.main import app


client = TestClient(app)


def test_llm_status_returns_disabled_without_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.get("/assistant/llm/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["api_key_configured"] is False


def test_llm_disabled_uses_rule_based_fallback(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")

    response = client.post("/assistant/chat", json={"message": "Was kannst du?"})

    assert response.status_code == 200
    assert response.json()["tool"] == "general_answer"
    assert response.json()["mode"] == "rule_based_fallback"


def test_llm_enabled_openai_error_falls_back_safely(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail_response(self, messages, tools):
        raise RuntimeError("openai unavailable")

    monkeypatch.setattr(
        "app.assistant.llm_client.LLMClient.create_response_with_tools",
        fail_response,
    )

    response = client.post("/assistant/chat", json={"message": "Was kannst du?"})

    assert response.status_code == 200
    assert "LLM-Anbindung ist aktuell nicht erreichbar" in response.json()["answer"]
    assert response.json()["mode"] == "rule_based_fallback"


def test_tool_schema_list_includes_ecoflow_energy_overview() -> None:
    schemas = ToolRegistry().get_openai_tool_schemas()

    assert any(schema["name"] == "ecoflow_energy_overview" for schema in schemas)


def test_execute_tool_blocks_red_action() -> None:
    result = ToolRegistry().execute_tool("email_send_blocked", {})

    assert result["blocked"] is True
    assert result["risk"] == ActionRisk.RED


def test_execute_tool_requires_confirmation_for_yellow_action() -> None:
    result = ToolRegistry().execute_tool("email_create_draft", {})

    assert result["confirmation_required"] is True
    assert result["risk"] == ActionRisk.YELLOW


def test_execute_tool_executes_green_action(monkeypatch) -> None:
    def fake_capabilities() -> dict[str, Any]:
        return {"capabilities": ["EcoFlow"]}

    registry = ToolRegistry()
    registry.register(
        "assistant_capabilities",
        "capabilities",
        ActionRisk.GREEN,
        fake_capabilities,
    )

    result = registry.execute_tool("assistant_capabilities", {})

    assert result["executed"] is True
    assert result["result"]["capabilities"] == ["EcoFlow"]


def test_assistant_capabilities_works() -> None:
    result = ToolRegistry().execute_tool("assistant_capabilities", {})

    assert result["executed"] is True
    assert "Gmail" in result["result"]["message"]


def test_gmail_unread_tool_maps_to_recent_unread_query(monkeypatch) -> None:
    captured = {}

    def fake_search(self, query, providers=None):
        captured["query"] = query
        return {"providers": [], "message": "ok"}

    monkeypatch.setattr(
        "app.tools.productivity.email_service.EmailService.search_emails",
        fake_search,
    )

    result = ToolRegistry().execute_tool("gmail_unread_recent", {})

    assert result["executed"] is True
    assert captured["query"] == "is:unread newer_than:30d"


def test_llm_can_execute_multiple_green_tools(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeLLMClient:
        def is_available(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def model_name(self) -> str:
            return "test-model"

        def create_response_with_tools(self, messages, tools):
            return {
                "tool_calls": [
                    {"id": "1", "name": "gmail_unread_recent", "arguments": {}},
                    {"id": "2", "name": "timetree_today", "arguments": {}},
                    {"id": "3", "name": "home_assistant_get_problems", "arguments": {}},
                    {"id": "4", "name": "ecoflow_energy_overview", "arguments": {}},
                ]
            }

        def final_response_with_tool_outputs(self, original_messages, tool_calls, tool_outputs):
            return {"text": "Zusammenfassung aus mehreren Werkzeugen."}

    registry = ToolRegistry()
    for name in (
        "gmail_unread_recent",
        "timetree_today",
        "home_assistant_get_problems",
        "ecoflow_energy_overview",
    ):
        registry.register(
            name,
            name,
            ActionRisk.GREEN,
            lambda name=name: {"tool": name},
        )

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Gibt es heute etwas Wichtiges?"
    )

    assert result["mode"] == "llm"
    assert result["answer"] == "Zusammenfassung aus mehreren Werkzeugen."
    assert len(result["tool_outputs"]) == 4


def test_dashboard_endpoint_still_works() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200


def test_ollama_provider_does_not_require_openai_api_key(monkeypatch) -> None:
    from app.assistant.llm_client import LLMClient

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")

    llm = LLMClient()

    assert llm.provider_name() == "ollama"
    assert llm.is_available() is True
    assert llm.model_name() == "qwen3:8b"


def test_llm_status_shows_ollama_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.get("/assistant/llm/status")

    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"
    assert response.json()["model"] == "qwen3:8b"
    assert response.json()["base_url"] == "http://localhost:11434/v1"
    assert response.json()["api_key_required"] is False


def test_ollama_status_endpoint_returns_200(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")

    def fake_get(url, timeout):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"models": [{"name": "qwen3:8b"}]}

        return Response()

    monkeypatch.setattr("app.main.requests.get", fake_get)

    response = client.get("/assistant/ollama/status")

    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"
    assert response.json()["reachable"] is True


def test_ollama_unavailable_returns_safe_response(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")

    def fail_get(url, timeout):
        raise RuntimeError("offline")

    monkeypatch.setattr("app.main.requests.get", fail_get)

    response = client.get("/assistant/ollama/status")

    assert response.status_code == 200
    assert response.json()["reachable"] is False
    assert "Ollama ist nicht erreichbar" in response.json()["message"]


def test_llm_test_uses_ollama_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")

    def fake_create_response(self, messages, tools):
        return {"text": "Hallo von Ollama.", "tool_calls": []}

    monkeypatch.setattr(
        "app.assistant.llm_client.LLMClient.create_response_with_tools",
        fake_create_response,
    )

    response = client.post("/assistant/llm/test", json={"message": "Sag Hallo"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Hallo von Ollama."


def test_provider_none_uses_fallback(monkeypatch) -> None:
    from app.assistant.llm_client import LLMClient

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    llm = LLMClient()

    assert llm.is_available() is False
    assert llm.mode() == "rule_based_fallback"


def test_llm_test_identity_answer_mentions_hammer_jarvis(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    def fake_create_response(self, messages, tools):
        assert messages[0]["role"] == "system"
        assert "Hammer Jarvis" in messages[0]["content"]
        return {
            "text": "Hallo! Ich bin ein KI-Assistent, der von Alibaba Cloud entwickelt wurde.",
            "tool_calls": [],
        }

    monkeypatch.setattr(
        "app.assistant.llm_client.LLMClient.create_response_with_tools",
        fake_create_response,
    )

    response = client.post(
        "/assistant/llm/test",
        json={"message": "Sag kurz Hallo und erklaere in einem Satz, was du bist."},
    )

    assert response.status_code == 200
    assert "Hammer Jarvis" in response.json()["answer"]
    assert "Alibaba" not in response.json()["answer"]


def test_assistant_chat_identity_returns_hammer_jarvis(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    class FakeLLMClient:
        def is_available(self) -> bool:
            return True

        def create_response_with_tools(self, messages, tools):
            assert messages[0]["role"] == "system"
            return {
                "text": "Ich bin Qwen, ein Modell von Alibaba Cloud.",
                "tool_calls": [],
            }

    result = AssistantOrchestrator(llm_client=FakeLLMClient()).handle_message("Wer bist du?")

    assert "Hammer Jarvis" in result["answer"]
    assert "Qwen" not in result["answer"]
    assert "Alibaba" not in result["answer"]


def test_sanitize_identity_response_corrects_base_model_identity() -> None:
    result = sanitize_identity_response(
        "Wer bist du?",
        "Ich bin ChatGPT von OpenAI.",
    )

    assert "Hammer Jarvis" in result
    assert "ChatGPT" not in result
    assert "OpenAI" not in result


def test_ecoflow_tool_executes_before_llm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    calls = []

    class FakeLLMClient:
        def is_available(self):
            return True

        def create_response_with_tools(self, messages, tools):
            calls.append("llm")
            return {"text": "Ich kann keine Echtzeitdaten von EcoFlow abrufen.", "tool_calls": []}

    registry = ToolRegistry()
    registry.register(
        "ecoflow_energy_overview",
        "EcoFlow",
        ActionRisk.GREEN,
        lambda: calls.append("tool") or _fake_ecoflow_result(),
    )

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Jarvis, was macht EcoFlow gerade?"
    )

    assert calls[0] == "tool"
    assert result["tool"] == "ecoflow_energy_overview"
    assert "keine Echtzeitdaten" not in result["answer"]


def test_battery_question_executes_ecoflow_tool(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    executed = []

    registry = ToolRegistry()
    registry.register(
        "ecoflow_energy_overview",
        "EcoFlow",
        ActionRisk.GREEN,
        lambda: executed.append("ecoflow") or _fake_ecoflow_result(),
    )

    class FakeLLMClient:
        def is_available(self):
            return False

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Wie voll ist die Batterie?"
    )

    assert executed == ["ecoflow"]
    assert "Batterie: 45 %" in result["answer"]


def test_new_email_question_executes_gmail_unread_recent(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    executed = []

    registry = ToolRegistry()
    registry.register(
        "gmail_unread_recent",
        "Gmail unread",
        ActionRisk.GREEN,
        lambda: executed.append("gmail") or _fake_gmail_result(),
    )

    class FakeLLMClient:
        def is_available(self):
            return False

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Habe ich neue E-Mails?"
    )

    assert executed == ["gmail"]
    assert result["executed_tool"] == "gmail_unread_recent"
    assert "Ich habe 2 Gmail-Nachrichten gefunden." in result["answer"]


def test_timetree_question_executes_timetree_today(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    executed = []

    registry = ToolRegistry()
    registry.register(
        "timetree_today",
        "TimeTree",
        ActionRisk.GREEN,
        lambda: executed.append("timetree") or _fake_timetree_result(),
    )

    class FakeLLMClient:
        def is_available(self):
            return False

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Was steht heute in TimeTree?"
    )

    assert executed == ["timetree"]
    assert result["tool"] == "timetree_today"
    assert "Heute stehen 1 TimeTree-Termine an" in result["answer"]


def test_home_assistant_offline_executes_problem_tool(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    executed = []

    registry = ToolRegistry()
    registry.register(
        "home_assistant_get_problems",
        "HA problems",
        ActionRisk.GREEN,
        lambda: executed.append("ha") or _fake_home_assistant_problems(),
    )

    class FakeLLMClient:
        def is_available(self):
            return False

    result = AssistantOrchestrator(registry=registry, llm_client=FakeLLMClient()).handle_message(
        "Welche Geräte sind offline?"
    )

    assert executed == ["ha"]
    assert result["tool"] == "home_assistant_get_problems"
    assert "Kritisch: 1, Warnungen: 1, Infos: 0" in result["answer"]


def test_tool_result_fallback_when_llm_summary_fails(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")

    class FailingLLMClient:
        def is_available(self):
            return True

        def create_response_with_tools(self, messages, tools):
            raise RuntimeError("llm failed")

    registry = ToolRegistry()
    registry.register(
        "ecoflow_energy_overview",
        "EcoFlow",
        ActionRisk.GREEN,
        lambda: _fake_ecoflow_result(),
    )

    result = AssistantOrchestrator(registry=registry, llm_client=FailingLLMClient()).handle_message(
        "Was macht EcoFlow gerade?"
    )

    assert result["tool"] == "ecoflow_energy_overview"
    assert "EcoFlow läuft" in result["answer"]


def test_ecoflow_formatter_removes_cjk_characters() -> None:
    result = _fake_ecoflow_result()
    result["human_status"]["details"][0] = "Batterie: 45 %充電"

    answer = format_ecoflow_energy_answer(result)

    assert "充電" not in answer
    assert sanitize_german_answer("Batterie: 45 %充電") == "Batterie: 45 %"


def test_ecoflow_formatter_does_not_interpret_unknown_battery_sign() -> None:
    answer = format_ecoflow_energy_answer(_fake_ecoflow_result())

    assert "lädt" not in answer.lower()
    assert "entlädt" not in answer.lower()
    assert "Batterieleistung roh" in answer
    assert "Richtung wird noch nicht interpretiert" in answer


def test_ecoflow_formatter_includes_battery_percent_and_top_warnings() -> None:
    result = _fake_ecoflow_result()
    result["warnings"] = [
        {"message": "Warnung 1"},
        {"message": "Warnung 2"},
        {"message": "Warnung 3"},
        {"message": "Warnung 4"},
    ]

    answer = format_ecoflow_energy_answer(result)

    assert "Batterie: 45 %" in answer
    assert "Warnung 1" in answer
    assert "Warnung 2" in answer
    assert "Warnung 3" in answer
    assert "Warnung 4" not in answer


def test_ecoflow_route_uses_deterministic_formatter_without_llm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")

    class ExplodingLLMClient:
        def is_available(self):
            return True

        def create_response_with_tools(self, messages, tools):
            raise AssertionError("EcoFlow responses must not be generated by LLM")

    registry = ToolRegistry()
    registry.register(
        "ecoflow_energy_overview",
        "EcoFlow",
        ActionRisk.GREEN,
        lambda: _fake_ecoflow_result(),
    )

    result = AssistantOrchestrator(registry=registry, llm_client=ExplodingLLMClient()).handle_message(
        "Was macht EcoFlow gerade?"
    )

    assert result["tool"] == "ecoflow_energy_overview"
    assert "Batterieleistung roh" in result["answer"]


def _fake_ecoflow_result() -> dict[str, Any]:
    return {
        "battery_power_w": -43.4,
        "human_status": {
            "headline": "EcoFlow läuft, aber einige Werte sind veraltet.",
            "details": [
                "Batterie: 45 %",
                "PV-Leistung: 0 W",
                "LAN Smart Meter: 10 W",
                "Netzleistung System: 129 W",
            ],
        },
        "battery_status": {
            "raw_value_w": -43.4,
            "sign_convention": "unknown",
            "interpretation": "unknown_charge_direction",
        },
        "warnings": [{"message": "Der Tageswert ist veraltet."}],
    }


def _fake_gmail_result() -> dict[str, Any]:
    return {
        "total_email_count": 2,
        "unread_count": 2,
        "providers": [
            {
                "provider": "gmail",
                "connected": True,
                "emails": [
                    {"sender": "Max", "subject": "Termin", "is_unread": True},
                    {"sender": "Lisa", "subject": "Update", "is_unread": True},
                ],
            }
        ],
        "message": "Ich habe 2 Gmail-Nachrichten gefunden.",
    }


def _fake_timetree_result() -> dict[str, Any]:
    return {
        "provider": "timetree",
        "enabled": True,
        "connected": True,
        "events": [
            {"title": "Familienessen", "start": "2026-06-05T18:00:00", "all_day": False}
        ],
    }


def _fake_home_assistant_problems() -> dict[str, Any]:
    return {
        "critical_count": 1,
        "warning_count": 1,
        "informational_count": 0,
        "critical": [{"entity_id": "sensor.bad", "state": "unavailable"}],
        "warning": [{"entity_id": "sensor.warn", "state": "unknown"}],
        "informational": [],
    }
