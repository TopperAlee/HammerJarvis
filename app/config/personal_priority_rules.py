import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PERSONAL_PRIORITY_RULES_PATH = Path(__file__).with_name("personal_priority_rules.json")
EMPTY_PERSONAL_PRIORITY_RULES = {"sender_rules": [], "subject_rules": []}
VALID_PRIORITIES = {"critical", "high", "medium", "low", "info"}


def load_personal_priority_rules(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    rules_path = _rules_path(path)
    try:
        with rules_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return _empty_rules()

    if not isinstance(data, dict):
        return _empty_rules()
    return _normalize_rules(data)


def save_personal_priority_rules(rules: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    normalized = _normalize_rules(rules)
    rules_path = _rules_path()
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    with rules_path.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return normalized


def add_sender_rule(match: str, priority: str, category: str, reason: str) -> dict[str, list[dict[str, Any]]]:
    return _add_rule("sender_rules", match, priority, category, reason)


def add_subject_rule(match: str, priority: str, category: str, reason: str) -> dict[str, list[dict[str, Any]]]:
    return _add_rule("subject_rules", match, priority, category, reason)


def remove_rule(match: str) -> dict[str, list[dict[str, Any]]]:
    normalized_match = match.strip().lower()
    rules = load_personal_priority_rules()
    for key in ("sender_rules", "subject_rules"):
        rules[key] = [
            item for item in rules[key] if str(item.get("match", "")).strip().lower() != normalized_match
        ]
    return save_personal_priority_rules(rules)


def _add_rule(key: str, match: str, priority: str, category: str, reason: str) -> dict[str, list[dict[str, Any]]]:
    rules = load_personal_priority_rules()
    normalized_match = match.strip().lower()
    if not normalized_match:
        raise ValueError("match darf nicht leer sein.")
    new_rule = {
        "match": normalized_match,
        "priority": _normalize_priority(priority),
        "category": category.strip() or "unknown",
        "reason": reason.strip() or "Persoenliche Prioritaetsregel.",
    }
    rules[key] = [
        item for item in rules[key] if str(item.get("match", "")).strip().lower() != normalized_match
    ]
    rules[key].append(new_rule)
    return save_personal_priority_rules(rules)


def _normalize_rules(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    normalized = _empty_rules()
    for key in ("sender_rules", "subject_rules"):
        values = data.get(key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            match = str(item.get("match", "")).strip()
            if not match:
                continue
            normalized[key].append(
                {
                    "match": match.lower(),
                    "priority": _normalize_priority(str(item.get("priority", "info"))),
                    "category": str(item.get("category", "unknown")).strip() or "unknown",
                    "reason": str(item.get("reason", "Persoenliche Prioritaetsregel.")).strip(),
                }
            )
    return normalized


def _normalize_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    return normalized if normalized in VALID_PRIORITIES else "info"


def _rules_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    configured = os.getenv("PERSONAL_PRIORITY_RULES_FILE")
    if configured:
        return Path(configured)
    return DEFAULT_PERSONAL_PRIORITY_RULES_PATH


def _empty_rules() -> dict[str, list[dict[str, Any]]]:
    return {key: list(value) for key, value in EMPTY_PERSONAL_PRIORITY_RULES.items()}
