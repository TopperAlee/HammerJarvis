import os
import time
from typing import Any

import requests

_SESSION = requests.Session()
_SAFE_RESPONSE_KEYS = {
    "provider",
    "model",
    "text",
    "output_length",
    "done",
    "done_reason",
    "total_duration_ms",
    "load_duration_ms",
    "prompt_eval_duration_ms",
    "eval_duration_ms",
    "ollama_total_duration_ms",
    "prompt_eval_count",
    "eval_count",
    "measured_http_duration_ms",
    "measured_total_duration_ms",
    "duration_ms",
}


class NativeOllamaClient:
    """Small wrapper around Ollama's native local HTTP API.

    This is intentionally read/generate only. It does not affect the
    ToolRegistry, permission model, or any Home Assistant write path.
    """

    def __init__(self, base_url: str | None = None) -> None:
        configured = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.base_url = configured.replace("/v1", "").rstrip("/")
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    def generate(self, prompt: str, model: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if options:
            payload["options"] = options
        method_started = time.perf_counter()
        http_started = time.perf_counter()
        response = _SESSION.post(f"{self.base_url}/api/generate", json=payload, timeout=_timeout_seconds())
        response.raise_for_status()
        measured_http_duration_ms = int((time.perf_counter() - http_started) * 1000)
        data = response.json()
        text = str(data.get("response", ""))
        return _sanitize_response(
            _with_timing_fields(
                {
                    "provider": "ollama",
                    "model": payload["model"],
                    "text": text,
                    "output_length": len(text),
                    "measured_http_duration_ms": measured_http_duration_ms,
                    "measured_total_duration_ms": int((time.perf_counter() - method_started) * 1000),
                    "duration_ms": int((time.perf_counter() - method_started) * 1000),
                    **data,
                }
            )
        )

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if options:
            payload["options"] = options
        method_started = time.perf_counter()
        http_started = time.perf_counter()
        response = _SESSION.post(f"{self.base_url}/api/chat", json=payload, timeout=_timeout_seconds())
        response.raise_for_status()
        measured_http_duration_ms = int((time.perf_counter() - http_started) * 1000)
        data = response.json()
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        text = str(message.get("content", ""))
        return _sanitize_response(
            _with_timing_fields(
                {
                    "provider": "ollama",
                    "model": payload["model"],
                    "text": text,
                    "output_length": len(text),
                    "measured_http_duration_ms": measured_http_duration_ms,
                    "measured_total_duration_ms": int((time.perf_counter() - method_started) * 1000),
                    "duration_ms": int((time.perf_counter() - method_started) * 1000),
                    **data,
                }
            )
        )

    def benchmark_model(self, model: str) -> dict[str, Any]:
        options = {
            "num_predict": 4 if "qwen" in model.lower() else _int_env("OLLAMA_BENCHMARK_NUM_PREDICT", 2),
            "temperature": 0,
            "num_ctx": _int_env("OLLAMA_BENCHMARK_NUM_CTX", 512),
        }
        result = self.generate("Antworte nur mit: OK", model=model, options=options)
        if result.get("output_length") == 0:
            result["warning"] = "Benchmark-Ausgabe leer; Modell benoetigte mehr Tokens oder anderes Chat-Template."
        return result

    def list_models(self) -> dict[str, Any]:
        try:
            response = _SESSION.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            installed = [str(item.get("name", "")) for item in models if isinstance(item, dict) and item.get("name")]
            return {"provider": "ollama", "reachable": True, "models": models, "installed_models": installed}
        except Exception:
            return {"provider": "ollama", "reachable": False, "models": [], "installed_models": []}

    def is_model_installed(self, model: str) -> bool:
        return model in set(self.list_models().get("installed_models") or [])


def _with_timing_fields(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            data[f"{key}_ms"] = int(value / 1_000_000)
    if "total_duration_ms" in data:
        data["ollama_total_duration_ms"] = data["total_duration_ms"]
    return data


def _sanitize_response(data: dict[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in _SAFE_RESPONSE_KEYS if key in data}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("OLLAMA_HTTP_TIMEOUT_SECONDS", os.getenv("OLLAMA_TIMEOUT_SECONDS", "60")))
    except ValueError:
        return 60.0
