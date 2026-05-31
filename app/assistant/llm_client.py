import os

from dotenv import load_dotenv


load_dotenv()


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self._mode = "openai_ready" if self.api_key else "rule_based_fallback"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def mode(self) -> str:
        return self._mode

    def generate_response(self, message: str) -> dict[str, str | bool]:
        if not self.api_key:
            return {
                "mode": self._mode,
                "available": False,
                "answer": (
                    "Ich kann diese Frage grundsaetzlich beantworten, sobald die "
                    "LLM-Anbindung aktiv ist. Aktuell kann ich sicher EcoFlow, "
                    "Home Assistant, vorbereitete Kalender- und E-Mail-Werkzeuge "
                    "sowie TimeTree-Status verarbeiten."
                ),
            }
        return {
            "mode": self._mode,
            "available": True,
            "answer": (
                "Die LLM-Anbindung ist vorbereitet, aber Tool Calling ist in v0.3 "
                "noch nicht aktiv geschaltet."
            ),
        }

    def answer(self, message: str) -> dict[str, str | bool]:
        return self.generate_response(message)
