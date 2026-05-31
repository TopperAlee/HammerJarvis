import os

from dotenv import load_dotenv


load_dotenv()


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.mode = "openai_ready" if self.api_key else "rule_based_fallback"

    def answer(self, message: str) -> dict[str, str]:
        if not self.api_key:
            return {
                "mode": self.mode,
                "answer": (
                    "Fuer freie Wissensfragen brauche ich als naechsten Schritt "
                    "die LLM-Anbindung. Die Tool-Struktur ist vorbereitet."
                ),
            }
        return {
            "mode": self.mode,
            "answer": (
                "Die LLM-Anbindung ist vorbereitet, aber Tool Calling ist in v0.3 "
                "noch nicht aktiv geschaltet."
            ),
        }
