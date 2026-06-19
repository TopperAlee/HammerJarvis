import re
from typing import Any


BLOCK_PATTERNS = (
    r"\bapi[_ -]?key\b",
    r"\bsk-[A-Za-z0-9_-]{8,}",
    r"\bbearer\s+[A-Za-z0-9._-]{8,}",
    r"\boauth\b.*\btoken\b",
    r"\bpassword\b",
    r"\bpasswort\b",
    r"\btoken\b",
    r"\bbank\s*(login|zugang)\b",
)
SENSITIVE_PATTERNS = (
    r"\bmedizin\b",
    r"\bdiagnose\b",
    r"\bkrankheit\b",
    r"\bsteueridentifikation\b",
)


class MemoryClassifier:
    """Classify explicit memory writes before storage.

    Memory is not a transcript sink. We block credentials and token-like data
    outright and mark sensitive personal data for confirmation before any write.
    """

    def classify_text(self, text: str) -> dict[str, Any]:
        lowered = str(text).lower()
        if any(re.search(pattern, lowered, re.I) for pattern in BLOCK_PATTERNS):
            return {
                "allowed": False,
                "blocked": True,
                "reason": "security_sensitive",
                "message": "Das speichere ich nicht als Gedächtnis, weil es sicherheitskritisch ist.",
            }
        if any(re.search(pattern, lowered, re.I) for pattern in SENSITIVE_PATTERNS):
            return {"allowed": True, "sensitive": True, "requires_confirmation": True}
        return {"allowed": True, "sensitive": False, "requires_confirmation": False}


def infer_memory_item(text: str) -> dict[str, Any]:
    cleaned = text.strip(" .!?:,")
    device_match = _device_relation(cleaned)
    if device_match:
        key, value = device_match
        domain = key.split(".", 1)[0]
        return {
            "type": "device",
            "key": key,
            "value": value,
            "tags": ["home_assistant", "smart_home", "alias", domain],
            "source": "user",
            "confidence": "high",
            "source_text": cleaned,
        }
    priority_match = re.search(r"(.+?)\s+unwichtig", cleaned, re.I)
    if priority_match:
        return {
            "type": "preference",
            "key": priority_match.group(1).strip(),
            "value": "low priority",
            "tags": ["preference"],
            "source": "user",
        }
    if ":" in cleaned:
        key, value = cleaned.split(":", 1)
        return {"type": "fact", "key": key.strip(), "value": value.strip(), "tags": [], "source": "user"}
    words = cleaned.split()
    key = " ".join(words[:4]) if words else "memory"
    return {"type": "fact", "key": key, "value": cleaned, "tags": [], "source": "user"}


def _title_value(value: str) -> str:
    cleaned = _clean_relation_value(value)
    if cleaned.lower() == "flurlicht":
        return "Flur Licht"
    return cleaned[:1].upper() + cleaned[1:]


def _device_relation(text: str) -> tuple[str, str] | None:
    entity = r"([a-z_]+\.[a-z0-9_]+)"
    patterns = (
        rf"^{entity}\s*=\s*(.+)$",
        rf"^{entity}\s+(?:ist|heißt|heisst|bedeutet|als)\s+(.+)$",
        rf"^{entity}\s+(.+?)\s+(?:ist|bedeutet|heißt|heisst)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text.strip(), re.I)
        if not match:
            continue
        key = match.group(1).lower()
        value = _title_value(match.group(2))
        if value:
            return key, value
    return None


def _clean_relation_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip(" .!?:,"))
    cleaned = re.sub(r"^(das|der|die|mein|meine|meinen|meiner)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+(ist|bedeutet|heißt|heisst)$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(das|der|die|mein|meine|meinen|meiner)\s+", "", cleaned, flags=re.I)
    return cleaned.strip(" .!?:,")


def normalize_relation_value(value: str) -> str:
    return _clean_relation_value(value)
