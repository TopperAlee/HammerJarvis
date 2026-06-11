import json
from pathlib import Path
from typing import Any


ALLOWLIST_PATH = Path(__file__).with_name("home_assistant_action_allowlist.json")
SAFE_ENTITY_DOMAINS = {"light", "switch"}
SAFE_ALLOWLIST_DOMAINS = {"light", "switch", "scene"}
SAFE_SCENE_DOMAIN = "scene"
ALLOWED_SERVICES = {"turn_on", "turn_off"}
SCENE_ALLOWED_SERVICES = {"turn_on"}
EMPTY_ALLOWLIST = {
    "allowed_entities": [],
    "allowed_scenes": [],
    "blocked_domains": [],
}


def load_home_assistant_action_allowlist() -> dict[str, Any]:
    """Load the local HA action allowlist; invalid or missing config fails closed."""
    try:
        with ALLOWLIST_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return dict(EMPTY_ALLOWLIST)
    if not isinstance(data, dict):
        return dict(EMPTY_ALLOWLIST)
    return {
        "allowed_entities": _list_or_empty(data.get("allowed_entities")),
        "allowed_scenes": _list_or_empty(data.get("allowed_scenes")),
        "blocked_domains": [str(item).lower() for item in _list_or_empty(data.get("blocked_domains"))],
    }


def is_entity_action_allowed(entity_id: str, action: str) -> bool:
    action = str(action).strip().lower()
    entity_id = str(entity_id).strip().lower()
    domain = _domain(entity_id)
    data = load_home_assistant_action_allowlist()
    if domain in set(data.get("blocked_domains", [])):
        return False
    if domain not in SAFE_ENTITY_DOMAINS or action not in ALLOWED_SERVICES:
        return False
    for entity in data.get("allowed_entities", []):
        if not isinstance(entity, dict):
            continue
        if str(entity.get("entity_id", "")).lower() != entity_id:
            continue
        configured_domain = str(entity.get("domain") or _domain(entity_id)).lower()
        allowed_actions = {str(item).lower() for item in entity.get("allowed_actions", [])}
        return configured_domain == domain and action in allowed_actions
    return False


def is_scene_allowed(scene_id: str) -> bool:
    scene_id = str(scene_id).strip().lower()
    if _domain(scene_id) != SAFE_SCENE_DOMAIN:
        return False
    data = load_home_assistant_action_allowlist()
    for scene in data.get("allowed_scenes", []):
        if isinstance(scene, str) and scene.lower() == scene_id:
            return True
        if isinstance(scene, dict) and str(scene.get("entity_id", "")).lower() == scene_id:
            return True
    return False


def get_allowed_actions() -> dict[str, Any]:
    data = load_home_assistant_action_allowlist()
    entities = [
        entity
        for entity in data.get("allowed_entities", [])
        if isinstance(entity, dict)
        and _domain(str(entity.get("entity_id", ""))) in SAFE_ENTITY_DOMAINS
        and _domain(str(entity.get("entity_id", ""))) not in set(data.get("blocked_domains", []))
    ]
    scenes = data.get("allowed_scenes", [])
    return {
        "allowed_entities": entities,
        "allowed_scenes": scenes,
        "blocked_domains": data.get("blocked_domains", []),
    }


def list_allowed_entities() -> list[dict[str, Any]]:
    return list(get_allowed_actions().get("allowed_entities", []))


def validate_entity_can_be_allowlisted(entity_id: str, domain: str) -> dict[str, Any]:
    """Validate allowlist changes fail closed; dangerous domains can never be added."""
    entity_id = str(entity_id).strip().lower()
    domain = str(domain or _domain(entity_id)).strip().lower()
    blocked_domains = set(load_home_assistant_action_allowlist().get("blocked_domains", []))
    if domain in blocked_domains or domain not in SAFE_ALLOWLIST_DOMAINS:
        return {
            "allowed": False,
            "reason": "domain_not_allowed",
            "message": "Diese Geräteklasse darf nicht freigegeben werden.",
        }
    if not entity_id.startswith(f"{domain}."):
        return {
            "allowed": False,
            "reason": "entity_domain_mismatch",
            "message": "Entity-ID und Domain passen nicht zusammen.",
        }
    return {"allowed": True}


def add_allowed_entity(
    entity_id: str,
    friendly_name: str,
    domain: str,
    allowed_actions: list[str],
) -> dict[str, Any]:
    validation = validate_entity_can_be_allowlisted(entity_id, domain)
    if not validation.get("allowed"):
        return {"blocked": True, **validation}
    entity_id = str(entity_id).strip().lower()
    domain = str(domain or _domain(entity_id)).strip().lower()
    safe_actions = _safe_actions_for_domain(domain, allowed_actions)
    if not safe_actions:
        return {
            "blocked": True,
            "reason": "action_not_allowed",
            "message": "Für diese Entity wurden keine sicheren Aktionen angegeben.",
        }
    data = load_home_assistant_action_allowlist()
    entities = [item for item in data.get("allowed_entities", []) if isinstance(item, dict)]
    for item in entities:
        if str(item.get("entity_id", "")).lower() == entity_id:
            item.update(
                {
                    "friendly_name": friendly_name or item.get("friendly_name") or entity_id,
                    "domain": domain,
                    "allowed_actions": safe_actions,
                }
            )
            _save_allowlist(data | {"allowed_entities": entities})
            return _allowlist_result("updated", item)
    entry = {
        "entity_id": entity_id,
        "friendly_name": friendly_name or entity_id,
        "domain": domain,
        "allowed_actions": safe_actions,
    }
    entities.append(entry)
    data["allowed_entities"] = entities
    _save_allowlist(data)
    return _allowlist_result("added", entry)


def remove_allowed_entity(entity_id: str) -> dict[str, Any]:
    entity_id = str(entity_id).strip().lower()
    data = load_home_assistant_action_allowlist()
    entities = [item for item in data.get("allowed_entities", []) if isinstance(item, dict)]
    remaining = [item for item in entities if str(item.get("entity_id", "")).lower() != entity_id]
    removed = len(remaining) != len(entities)
    data["allowed_entities"] = remaining
    _save_allowlist(data)
    return {
        "removed": removed,
        "entity_id": entity_id,
        "message": (
            f"{entity_id} wurde aus der Smart-Home-Freigabe entfernt."
            if removed
            else f"{entity_id} war nicht in der Smart-Home-Freigabe enthalten."
        ),
    }


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0].lower() if "." in entity_id else ""


def _safe_actions_for_domain(domain: str, actions: list[str]) -> list[str]:
    requested = {str(action).lower() for action in actions}
    allowed = SCENE_ALLOWED_SERVICES if domain == SAFE_SCENE_DOMAIN else ALLOWED_SERVICES
    return [action for action in ("turn_on", "turn_off") if action in requested and action in allowed]


def _save_allowlist(data: dict[str, Any]) -> None:
    normalized = {
        "allowed_entities": _list_or_empty(data.get("allowed_entities")),
        "allowed_scenes": _list_or_empty(data.get("allowed_scenes")),
        "blocked_domains": [str(item).lower() for item in _list_or_empty(data.get("blocked_domains"))],
    }
    ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _allowlist_result(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    action_words = ", ".join(entry.get("allowed_actions", []))
    return {
        key: True,
        "entity_id": entry["entity_id"],
        "friendly_name": entry.get("friendly_name", entry["entity_id"]),
        "domain": entry.get("domain", _domain(entry["entity_id"])),
        "allowed_actions": entry.get("allowed_actions", []),
        "message": (
            f"{entry.get('friendly_name', entry['entity_id'])} wurde zur Smart-Home-Freigabe hinzugefügt. "
            f"Aktionen: {action_words}. Trotz Freigabe braucht jede Ausführung weiterhin Bestätigung."
        ),
    }
