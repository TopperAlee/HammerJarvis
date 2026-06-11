from typing import Any

import requests

from app.config.home_assistant_action_allowlist import (
    ALLOWED_SERVICES,
    add_allowed_entity,
    get_allowed_actions,
    is_entity_action_allowed,
    is_scene_allowed,
    remove_allowed_entity,
)
from app.config.settings import get_settings
from app.tools.home_assistant import HomeAssistantTool


ACTION_MESSAGES = {
    "turn_on": "eingeschaltet",
    "turn_off": "ausgeschaltet",
}


class HomeAssistantActionTool:
    """Safety layer for limited Home Assistant writes.

    This tool intentionally accepts only canonical actions mapped to fixed Home
    Assistant services. It never accepts arbitrary service names from the user.
    """

    def list_allowed_actions(self) -> dict[str, Any]:
        actions = get_allowed_actions()
        count = len(actions.get("allowed_entities", [])) + len(actions.get("allowed_scenes", []))
        message = (
            f"{count} Smart-Home-Aktion(en) sind freigegeben."
            if count
            else "Aktuell sind keine Smart-Home-Aktionen freigegeben."
        )
        return {
            "provider": "home_assistant",
            "enabled": True,
            **actions,
            "count": count,
            "message": message,
        }

    def discover_actionable_entities(self) -> dict[str, Any]:
        """Read HA states and suggest candidates only; discovery never modifies or switches devices."""
        states = HomeAssistantTool().get_all_states()
        candidates: list[dict[str, Any]] = []
        blocked_count = 0
        for item in states:
            entity_id = str(item.get("entity_id", ""))
            domain = _domain(entity_id)
            if domain in _blocked_domains():
                blocked_count += 1
                continue
            if domain not in {"light", "switch", "scene"}:
                continue
            friendly_name = str(item.get("attributes", {}).get("friendly_name") or entity_id)
            candidates.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "domain": domain,
                    "suggested_actions": ["turn_on"] if domain == "scene" else ["turn_on", "turn_off"],
                    "risk": "YELLOW",
                }
            )
        return {
            "provider": "home_assistant",
            "candidates": candidates,
            "blocked_count": blocked_count,
            "message": f"{len(candidates)} schaltbare Kandidat(en) gefunden.",
        }

    def add_to_allowlist(
        self,
        entity_id: str,
        friendly_name: str,
        domain: str,
        allowed_actions: list[str],
    ) -> dict[str, Any]:
        return add_allowed_entity(entity_id, friendly_name, domain, allowed_actions)

    def remove_from_allowlist(self, entity_id: str) -> dict[str, Any]:
        return remove_allowed_entity(entity_id)

    def find_actionable_candidate(self, name_or_id: str) -> dict[str, Any] | None:
        query = _normalize(name_or_id)
        for candidate in self.discover_actionable_entities().get("candidates", []):
            if query in {
                _normalize(str(candidate.get("entity_id", ""))),
                _normalize(str(candidate.get("friendly_name", ""))),
            } or query in _normalize(str(candidate.get("friendly_name", ""))):
                return candidate
        return None

    def prepare_home_assistant_action(self, entity_name_or_id: str, action: str) -> dict[str, Any]:
        canonical_action = _canonical_action(action)
        if canonical_action not in ALLOWED_SERVICES:
            return _blocked("action_not_allowed")
        resolved = _resolve_allowed_target(entity_name_or_id)
        if not resolved:
            return _blocked("entity_not_allowlisted")

        entity_id = resolved["entity_id"]
        if _domain(entity_id) == "scene":
            if canonical_action != "turn_on" or not is_scene_allowed(entity_id):
                return _blocked("entity_not_allowlisted")
        elif not is_entity_action_allowed(entity_id, canonical_action):
            return _blocked("entity_not_allowlisted")

        title = _action_title(resolved, canonical_action)
        return {
            "prepared": True,
            "entity_id": entity_id,
            "friendly_name": resolved.get("friendly_name") or entity_id,
            "action": canonical_action,
            "title": title,
            "message": f"Ich kann {title}. Diese Aktion benötigt Bestätigung.",
        }

    def execute_home_assistant_action(self, entity_id: str, action: str) -> dict[str, Any]:
        """Execute an allowlisted write. ToolRegistry marks this YELLOW and requires confirmation."""
        canonical_action = _canonical_action(action)
        entity_id = str(entity_id).strip().lower()
        if canonical_action not in ALLOWED_SERVICES:
            return _blocked("action_not_allowed")
        domain = _domain(entity_id)
        if domain == "scene":
            if canonical_action != "turn_on" or not is_scene_allowed(entity_id):
                return _blocked("entity_not_allowlisted")
        elif not is_entity_action_allowed(entity_id, canonical_action):
            return _blocked("entity_not_allowlisted")

        settings = get_settings().require_home_assistant()
        assert settings.home_assistant_url is not None
        assert settings.home_assistant_token is not None
        url = f"{settings.home_assistant_url.rstrip('/')}/api/services/{domain}/{canonical_action}"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.home_assistant_token}",
                "Content-Type": "application/json",
            },
            json={"entity_id": entity_id},
            timeout=10,
        )
        response.raise_for_status()
        friendly_name = _friendly_name(entity_id)
        return {
            "executed": True,
            "entity_id": entity_id,
            "action": canonical_action,
            "message": f"{friendly_name} wurde {ACTION_MESSAGES.get(canonical_action, 'geschaltet')}.",
        }


def _resolve_allowed_target(entity_name_or_id: str) -> dict[str, Any] | None:
    query = _normalize(entity_name_or_id)
    actions = get_allowed_actions()
    for entity in actions.get("allowed_entities", []):
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("entity_id", ""))
        friendly_name = str(entity.get("friendly_name", ""))
        if query in {_normalize(entity_id), _normalize(friendly_name)} or query in _normalize(friendly_name):
            return entity
    for scene in actions.get("allowed_scenes", []):
        if isinstance(scene, str):
            entity = {"entity_id": scene, "friendly_name": scene, "domain": "scene", "allowed_actions": ["turn_on"]}
        elif isinstance(scene, dict):
            entity = scene
        else:
            continue
        entity_id = str(entity.get("entity_id", ""))
        friendly_name = str(entity.get("friendly_name", ""))
        if query in {_normalize(entity_id), _normalize(friendly_name)} or query in _normalize(friendly_name):
            return entity
    return None


def _canonical_action(action: str) -> str:
    normalized = _normalize(action)
    if normalized in {"turn_on", "on", "ein", "an", "einschalten", "anschalten", "aktivieren"}:
        return "turn_on"
    if normalized in {"turn_off", "off", "aus", "ausschalten"}:
        return "turn_off"
    return normalized


def _action_title(entity: dict[str, Any], action: str) -> str:
    name = str(entity.get("friendly_name") or entity.get("entity_id"))
    verb = "einschalten" if action == "turn_on" else "ausschalten"
    if _domain(str(entity.get("entity_id", ""))) == "scene":
        verb = "aktivieren"
    return f"{name} {verb}"


def _friendly_name(entity_id: str) -> str:
    resolved = _resolve_allowed_target(entity_id)
    if resolved:
        return str(resolved.get("friendly_name") or entity_id)
    return entity_id


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "blocked": True,
        "reason": reason,
        "message": "Diese Home-Assistant-Aktion ist nicht freigegeben.",
    }


def _blocked_domains() -> set[str]:
    return set(get_allowed_actions().get("blocked_domains", []))


def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0].lower() if "." in entity_id else ""


def _normalize(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
