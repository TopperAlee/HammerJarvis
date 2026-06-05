import os
import re
from typing import Any

from dotenv import load_dotenv

from app.assistant.response_parser import extract_text, extract_tool_calls
from app.assistant.system_prompt import SYSTEM_PROMPT


load_dotenv()


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")

    def is_enabled(self) -> bool:
        return os.getenv("LLM_ENABLED", "false").strip().lower() == "true"

    def provider_name(self) -> str:
        return os.getenv("LLM_PROVIDER", "openai").strip().lower() or "none"

    def is_available(self) -> bool:
        if not self.is_enabled():
            return False
        provider = self.provider_name()
        if provider == "ollama":
            return True
        if provider == "openai":
            return bool(self.api_key)
        return False

    def model_name(self) -> str:
        if self.provider_name() == "ollama":
            return os.getenv("OLLAMA_MODEL", "qwen3:8b")
        return os.getenv("OPENAI_MODEL", "gpt-5.2")

    def base_url(self) -> str | None:
        if self.provider_name() == "ollama":
            return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return None

    def api_key_required(self) -> bool:
        return self.provider_name() == "openai"

    def mode(self) -> str:
        if not self.is_available():
            return "rule_based_fallback"
        return f"{self.provider_name()}_ready"

    def generate_response(self, message: str) -> dict[str, str | bool]:
        if not self.is_available():
            return {
                "mode": "rule_based_fallback",
                "available": False,
                "answer": (
                    "Ich kann diese Frage grundsaetzlich beantworten, sobald die "
                    "LLM-Anbindung aktiv ist. Aktuell kann ich sicher EcoFlow, "
                    "Home Assistant, vorbereitete Kalender- und E-Mail-Werkzeuge "
                    "sowie TimeTree-Status verarbeiten."
                ),
            }
        return {
            "mode": self.mode(),
            "available": True,
            "answer": "Die LLM-Anbindung ist aktiv.",
        }

    def answer(self, message: str) -> dict[str, str | bool]:
        return self.generate_response(message)

    def create_response_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.is_available():
            return {
                "mode": "rule_based_fallback",
                "available": False,
                "text": self.generate_response("")["answer"],
                "tool_calls": [],
            }

        if self.provider_name() == "ollama":
            return self._ollama_chat_completion(messages)

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model_name(),
            input=messages,
            tools=tools,
        )
        return {
            "raw": response,
            "text": extract_text(response),
            "tool_calls": extract_tool_calls(response),
        }

    def final_response_with_tool_outputs(
        self,
        original_messages: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        tool_outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.is_available():
            return {
                "mode": "rule_based_fallback",
                "available": False,
                "text": self.generate_response("")["answer"],
            }

        if self.provider_name() == "ollama":
            summary_messages = [
                *original_messages,
                {
                    "role": "user",
                    "content": (
                        "Fasse diese lokalen Werkzeugergebnisse auf Deutsch zusammen: "
                        f"{tool_outputs}"
                    ),
                },
            ]
            return self._ollama_chat_completion(summary_messages)

        from openai import OpenAI

        tool_messages = [
            {
                "role": "tool",
                "tool_call_id": output.get("tool_call_id"),
                "content": str(output.get("output", {})),
            }
            for output in tool_outputs
        ]
        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model_name(),
            input=[*original_messages, *tool_messages],
        )
        return {"raw": response, "text": extract_text(response)}

    def _ollama_chat_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        from openai import OpenAI

        messages_with_system = _ensure_system_prompt(messages)
        client = OpenAI(
            base_url=self.base_url(),
            api_key=os.getenv("OLLAMA_API_KEY", "ollama") or "ollama",
        )
        response = client.chat.completions.create(
            model=self.model_name(),
            messages=messages_with_system,
            temperature=0.2,
        )
        user_message = _last_user_message(messages_with_system)
        text = sanitize_identity_response(
            user_message,
            response.choices[0].message.content or "",
        )
        return {"raw": response, "text": text, "tool_calls": []}


def sanitize_identity_response(user_message: str, text: str) -> str:
    if not _is_identity_question(user_message):
        return text
    if not _contains_base_model_identity(text):
        return text
    return (
        "Ich bin Hammer Jarvis, dein lokaler KI-Assistent. Ich laufe lokal "
        "auf deinem Windows-PC und nutze deine angebundenen Werkzeuge wie "
        "Home Assistant, EcoFlow, Gmail und TimeTree."
    )


def sanitize_german_answer(text: str) -> str:
    without_cjk = re.sub(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]+", "", text)
    without_mojibake_cjk = re.sub(r"(?:å|æ|ç|è|é|ê|ë|電|充|話|語|中|日|韓)[^\s.,;:!?)]*", "", without_cjk)
    cleaned_lines = [re.sub(r"[ \t]{2,}", " ", line).rstrip() for line in without_mojibake_cjk.splitlines()]
    return "\n".join(cleaned_lines).strip()


def _ensure_system_prompt(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if messages and messages[0].get("role") == "system":
        return messages
    return [{"role": "system", "content": SYSTEM_PROMPT}, *messages]


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _is_identity_question(message: str) -> bool:
    normalized = message.strip().lower()
    return any(
        term in normalized
        for term in (
            "wer bist du",
            "was bist du",
            "stell dich vor",
            "erkläre in einem satz, was du bist",
            "erklaere in einem satz, was du bist",
        )
    )


def _contains_base_model_identity(text: str) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in ("Alibaba", "Qwen", "OpenAI", "ChatGPT"))
