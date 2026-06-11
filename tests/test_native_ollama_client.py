from typing import Any

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_native_ollama_generate_includes_keep_alive(monkeypatch) -> None:
    from app.assistant.llm.native_ollama_client import NativeOllamaClient

    captured: dict[str, Any] = {}
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "30m")

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Response({"response": "OK", "total_duration": 1_000_000})

    monkeypatch.setattr("app.assistant.llm.native_ollama_client._SESSION.post", fake_post)

    result = NativeOllamaClient().generate("Antworte nur mit: OK", model="llama3.2:3b")

    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["stream"] is False
    assert captured["json"]["keep_alive"] == "30m"
    assert result["text"] == "OK"


def test_native_ollama_benchmark_sends_short_options(monkeypatch) -> None:
    from app.assistant.llm.native_ollama_client import NativeOllamaClient

    captured: dict[str, Any] = {}
    monkeypatch.setenv("OLLAMA_BENCHMARK_NUM_PREDICT", "2")
    monkeypatch.setenv("OLLAMA_BENCHMARK_NUM_CTX", "512")

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _Response(
            {
                "response": "OK",
                "context": [1, 2, 3, 4],
                "total_duration": 4_310_000_000,
                "load_duration": 4_207_000_000,
                "prompt_eval_duration": 78_000_000,
                "eval_duration": 18_000_000,
                "prompt_eval_count": 12,
                "eval_count": 2,
            }
        )

    monkeypatch.setattr("app.assistant.llm.native_ollama_client._SESSION.post", fake_post)

    result = NativeOllamaClient().benchmark_model("llama3.2:3b")

    assert captured["json"]["options"]["num_predict"] == 2
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["json"]["options"]["num_ctx"] == 512
    assert result["total_duration_ms"] == 4310
    assert result["load_duration_ms"] == 4207
    assert result["prompt_eval_duration_ms"] == 78
    assert result["eval_duration_ms"] == 18
    assert result["ollama_total_duration_ms"] == 4310
    assert "measured_http_duration_ms" in result
    assert "measured_total_duration_ms" in result
    assert "context" not in result


def test_native_ollama_chat_returns_message_text(monkeypatch) -> None:
    from app.assistant.llm.native_ollama_client import NativeOllamaClient

    captured: dict[str, Any] = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Response({"message": {"content": "Hallo"}, "total_duration": 2_000_000})

    monkeypatch.setattr("app.assistant.llm.native_ollama_client._SESSION.post", fake_post)

    result = NativeOllamaClient().chat([{"role": "user", "content": "Hallo"}], model="llama3.2:3b")

    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["keep_alive"]
    assert result["text"] == "Hallo"


def test_llm_native_api_uses_native_client_when_enabled(monkeypatch) -> None:
    from app.assistant.llm_client import LLMClient

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_USE_NATIVE_API", "true")

    def fake_chat(self, messages, model=None, options=None):
        return {"text": "Native OK", "model": model, "total_duration_ms": 12}

    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.chat", fake_chat)

    result = LLMClient().create_response_with_tools([{"role": "user", "content": "Hallo"}], [])

    assert result["text"] == "Native OK"
    assert result["mode"] == "ollama_native"


def test_llm_native_api_false_preserves_openai_compatible_path(monkeypatch) -> None:
    from app.assistant.llm_client import LLMClient

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_USE_NATIVE_API", "false")

    called = []

    def fake_ollama(self, messages, model=None):
        called.append("openai_compatible")
        return {"text": "Compat OK", "tool_calls": []}

    monkeypatch.setattr("app.assistant.llm_client.LLMClient._ollama_chat_completion", fake_ollama)

    result = LLMClient().create_response_with_tools([{"role": "user", "content": "Hallo"}], [])

    assert called == ["openai_compatible"]
    assert result["text"] == "Compat OK"


def test_native_warm_benchmark_returns_cold_and_warm(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "llama3.2:3b")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_MODEL_SMART", "qwen3:8b")

    def fake_list_models(self):
        return {"reachable": True, "models": [{"name": "llama3.2:3b"}], "installed_models": ["llama3.2:3b"]}

    results = [
        {"model": "llama3.2:3b", "duration_ms": 6500, "output_length": 2, "load_duration_ms": 4200, "total_duration_ms": 4310},
        {"model": "llama3.2:3b", "duration_ms": 500, "output_length": 2, "load_duration_ms": 300, "total_duration_ms": 498},
    ]

    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.list_models", fake_list_models)
    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.benchmark_model", lambda self, model: results.pop(0))

    response = client.get("/assistant/ollama/benchmark/warm")

    assert response.status_code == 200
    data = response.json()
    assert data["cold_result"]["duration_ms"] == 6500
    assert data["warm_result"]["duration_ms"] == 500
    assert "Cold Start" in data["interpretation"]


def test_native_warm_benchmark_uses_one_model_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "llama3.2:3b")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    calls = []

    monkeypatch.setattr(
        "app.assistant.llm.native_ollama_client.NativeOllamaClient.list_models",
        lambda self: {"reachable": True, "installed_models": ["llama3.2:3b", "qwen3:8b"], "models": []},
    )

    def fake_benchmark(self, model):
        calls.append(model)
        return {"model": model, "measured_total_duration_ms": 500, "measured_http_duration_ms": 490, "output_length": 2}

    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.benchmark_model", fake_benchmark)

    response = client.get("/assistant/ollama/benchmark/warm")

    assert response.status_code == 200
    assert calls == ["llama3.2:3b", "llama3.2:3b"]


def test_native_benchmark_current_model_only_and_tags_once(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "llama3.2:3b")
    list_calls = []
    benchmark_calls = []

    def fake_list_models(self):
        list_calls.append("tags")
        return {"reachable": True, "installed_models": ["qwen3:8b", "llama3.2:3b"], "models": []}

    def fake_benchmark(self, model):
        benchmark_calls.append(model)
        return {"model": model, "measured_total_duration_ms": 500, "measured_http_duration_ms": 490, "output_length": 2}

    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.list_models", fake_list_models)
    monkeypatch.setattr("app.assistant.llm.native_ollama_client.NativeOllamaClient.benchmark_model", fake_benchmark)

    response = client.get("/assistant/ollama/benchmark/native?models=current")

    assert response.status_code == 200
    assert list_calls == ["tags"]
    assert benchmark_calls == ["qwen3:8b"]


def test_native_benchmark_removes_context_from_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setattr(
        "app.assistant.llm.native_ollama_client.NativeOllamaClient.list_models",
        lambda self: {"reachable": True, "installed_models": ["llama3.2:3b"], "models": []},
    )
    monkeypatch.setattr(
        "app.assistant.llm.native_ollama_client.NativeOllamaClient.benchmark_model",
        lambda self, model: {"model": model, "context": [1, 2, 3], "measured_total_duration_ms": 500, "measured_http_duration_ms": 490, "output_length": 2},
    )

    response = client.get("/assistant/ollama/benchmark/native")

    assert response.status_code == 200
    assert "context" not in str(response.json())


def test_ollama_status_includes_native_keepalive_and_warmup(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "30m")
    monkeypatch.setenv("OLLAMA_USE_NATIVE_API", "true")
    monkeypatch.setenv("OLLAMA_WARMUP_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_WARMUP_ON_STARTUP", "true")

    def fake_get(url, timeout):
        return _Response({"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:3b"}]})

    monkeypatch.setattr("app.main.requests.get", fake_get)

    response = client.get("/assistant/ollama/status")

    assert response.status_code == 200
    data = response.json()
    assert data["keep_alive"] == "30m"
    assert data["native_api_enabled"] is True
    assert data["warmup_enabled"] is True
    assert data["warmup_on_startup"] is True


def test_performance_advice_detects_cold_start_pattern(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main._last_native_warm_benchmark",
        {
            "cold_result": {"duration_ms": 6500, "load_duration_ms": 4200},
            "warm_result": {"duration_ms": 500, "load_duration_ms": 300},
        },
    )
    monkeypatch.setattr("app.main.assistant_ollama_status", lambda: {"reachable": True, "fast_model_installed": True, "smart_model_installed": True})

    response = client.get("/assistant/ollama/performance-advice")

    assert response.status_code == 200
    assert any("keep_alive" in item or "Warmup" in item for item in response.json()["advice"])


def test_performance_advice_detects_jarvis_overhead(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main._last_native_benchmark",
        {
            "benchmarks": [
                {
                    "model": "llama3.2:3b",
                    "measured_http_duration_ms": 2500,
                    "ollama_total_duration_ms": 500,
                }
            ]
        },
    )
    monkeypatch.setattr("app.main.assistant_ollama_status", lambda: {"reachable": True, "fast_model_installed": True, "smart_model_installed": True})

    response = client.get("/assistant/ollama/performance-advice")

    assert response.status_code == 200
    assert any("deutlichen Overhead" in item for item in response.json()["advice"])


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload
