from __future__ import annotations

from typing import Any


DEFAULT_ACCEPTED_TRANSCRIPTS = ("Jarvis", "Jervis", "Dschawis")


def normalize_recognizer_inventory(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in items:
        normalized.append(
            {
                "id": str(item.get("id") or item.get("Id") or ""),
                "name": str(item.get("name") or item.get("Name") or ""),
                "culture": str(item.get("culture") or item.get("Culture") or ""),
                "description": str(item.get("description") or item.get("Description") or ""),
            }
        )
    return normalized


def choose_recognizer_culture(inventory: list[dict[str, Any]], requested: str) -> dict[str, Any]:
    normalized = normalize_recognizer_inventory(inventory)
    cultures = [item["culture"] for item in normalized if item["culture"]]
    requested_clean = (requested or "auto").strip()
    if requested_clean.casefold() == "auto":
        for culture in ("de-DE", "en-US"):
            match = _find_culture(normalized, culture)
            if match:
                return match
        return normalized[0] if normalized else {"error": "recognizer_unavailable", "installed_cultures": []}
    match = _find_culture(normalized, requested_clean)
    if match:
        return match
    return {"error": "culture_not_installed", "requested_culture": requested_clean, "installed_cultures": cultures}


def clean_accepted_transcripts(value: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_ACCEPTED_TRANSCRIPTS
    raw_items = value.split(",") if isinstance(value, str) else list(value)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        phrase = " ".join(str(item).strip().split())
        if not phrase:
            continue
        if phrase.casefold() == "hey jarvis":
            continue
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(phrase)
    return tuple(cleaned) or ("Jarvis",)


def build_transcript_semantics(transcripts: tuple[str, ...] | list[str]) -> dict[str, str]:
    return {transcript: "Jarvis" for transcript in clean_accepted_transcripts(tuple(transcripts))}


def _find_culture(items: list[dict[str, str]], culture: str) -> dict[str, str] | None:
    for item in items:
        if item.get("culture", "").casefold() == culture.casefold():
            return item
    return None
