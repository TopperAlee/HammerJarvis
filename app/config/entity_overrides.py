import json
from pathlib import Path
from typing import Any


DEFAULT_OVERRIDES_PATH = Path(__file__).with_name("entity_overrides.json")
EMPTY_OVERRIDES = {"ignored_entities": [], "downgraded_entities": []}


def load_entity_overrides(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    overrides_path = path or DEFAULT_OVERRIDES_PATH
    try:
        with overrides_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return EMPTY_OVERRIDES.copy()

    if not isinstance(data, dict):
        return EMPTY_OVERRIDES.copy()

    ignored_entities = data.get("ignored_entities", [])
    downgraded_entities = data.get("downgraded_entities", [])
    if not isinstance(ignored_entities, list):
        ignored_entities = []
    if not isinstance(downgraded_entities, list):
        downgraded_entities = []

    return {
        "ignored_entities": [
            item for item in ignored_entities if isinstance(item, dict)
        ],
        "downgraded_entities": [
            item for item in downgraded_entities if isinstance(item, dict)
        ],
    }


def is_ignored_entity(entity_id: str) -> bool:
    return get_ignore_reason(entity_id) is not None


def get_ignore_reason(entity_id: str) -> str | None:
    normalized = entity_id.strip().lower()
    for item in load_entity_overrides()["ignored_entities"]:
        if str(item.get("entity_id", "")).strip().lower() == normalized:
            reason = item.get("reason")
            return str(reason) if reason else None
    return None
