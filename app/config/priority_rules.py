import json
from pathlib import Path
from typing import Any


DEFAULT_PRIORITY_RULES_PATH = Path(__file__).with_name("priority_rules.json")

DEFAULT_PRIORITY_RULES = {
    "email_high_keywords": [
        "security",
        "sicherheit",
        "oauth",
        "login",
        "rechnung",
        "frist",
        "deadline",
        "fernakademie",
        "online-plattform",
    ],
    "email_medium_keywords": ["job", "stellenangebot", "linkedin", "termin", "reminder"],
    "email_low_senders": ["linkedin", "campact", "eventim", "newsletter"],
    "email_suspicious_keywords": ["hot-stock", "500%", "neu-kauf", "schnell sein", "depotwert"],
}


def load_priority_rules(path: Path | None = None) -> dict[str, list[str]]:
    rules_path = path or DEFAULT_PRIORITY_RULES_PATH
    try:
        with rules_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {key: list(value) for key, value in DEFAULT_PRIORITY_RULES.items()}

    if not isinstance(data, dict):
        return {key: list(value) for key, value in DEFAULT_PRIORITY_RULES.items()}

    rules: dict[str, list[str]] = {}
    for key, default_value in DEFAULT_PRIORITY_RULES.items():
        value = data.get(key, default_value)
        if not isinstance(value, list):
            value = default_value
        rules[key] = [str(item).lower() for item in value]
    return rules


def as_search_text(*values: Any) -> str:
    return " ".join(str(value or "").lower() for value in values)
