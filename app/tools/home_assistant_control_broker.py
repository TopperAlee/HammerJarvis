import os
import re
from typing import Any

import requests

from app.config.home_assistant_control_policy import (
    classify_action_risk,
    evaluate_auto_execution,
    load_home_assistant_control_policy,
    validate_control_request,
)
from app.config.settings import get_settings
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant_entities import HomeAssistantEntityCatalog


SERVICE_MAP = {
    "light": {"turn_on": "turn_on", "turn_off": "turn_off", "toggle": "toggle"},
    "switch": {"turn_on": "turn_on", "turn_off": "turn_off", "toggle": "toggle"},
    "scene": {"turn_on": "turn_on"},
    "script": {"turn_on": "turn_on"},
    "automation": {"turn_on": "turn_on", "turn_off": "turn_off"},
    "cover": {"open_cover": "open_cover", "close_cover": "close_cover", "stop_cover": "stop_cover"},
    "climate": {"set_temperature": "set_temperature"},
}


class HomeAssistantControlBroker:
    """Universal control broker with explicit service mappings and policy gates.

    The broker never accepts arbitrary Home Assistant service names or raw LLM
    payloads. It resolves intent, validates against the local policy and only
    executes fixed domain/action mappings after confirmation through the
    ToolRegistry/ActionExecutor boundary.
    """

    def __init__(self) -> None:
        self.catalog = HomeAssistantEntityCatalog()

    def list_control_policy(self) -> dict[str, Any]:
        return load_home_assistant_control_policy()

    def list_auto_policy(self) -> dict[str, Any]:
        policy = load_home_assistant_control_policy()
        return {
            "control_mode": policy.get("control_mode"),
            "auto_execute_enabled": bool(policy.get("auto_execute_enabled")),
            "auto_execute_domains": policy.get("auto_execute_domains", {}),
            "require_confirmation_domains": policy.get("require_confirmation_domains", []),
            "blocked_domains": policy.get("blocked_domains", []),
            "trusted_switches": policy.get("trusted_switches", []),
        }

    def list_trusted_switches(self) -> dict[str, Any]:
        switches = [item for item in load_home_assistant_control_policy().get("trusted_switches", []) if isinstance(item, dict)]
        return {"provider": "home_assistant", "count": len(switches), "trusted_switches": switches}

    def list_controllable_entities(self, domain: str | None = None) -> dict[str, Any]:
        catalog = self.catalog.list_entities(domain=domain, limit=500)
        entities = []
        for entity in catalog.get("entities", []):
            domain_name = str(entity.get("domain") or "")
            domain_policy = load_home_assistant_control_policy().get("domains", {}).get(domain_name, {})
            if domain_policy.get("enabled") and domain_name in SERVICE_MAP:
                entities.append({**entity, "allowed_actions": domain_policy.get("allowed_actions", [])})
        return {"provider": "home_assistant", "count": len(entities), "entities": entities}

    def resolve_control_intent(self, command: str) -> dict[str, Any]:
        action = _action_from_command(command)
        parameters = _parameters_from_command(command, action)
        if _is_all_lights_command(command):
            return self.prepare_batch_action(domain="light", action="turn_off" if "aus" in _norm(command) else "turn_on")
        if not action:
            return {"resolved": False, "blocked": True, "reason": "action_not_supported", "message": "Ich erkenne keine sichere Home-Assistant-Aktion."}
        query = _target_from_command(command, action)
        candidates = self._find_entities(query, domain="climate" if action == "set_temperature" else None)
        if not candidates:
            if action == "set_temperature":
                return {
                    "resolved": False,
                    "blocked": True,
                    "reason": "climate_entity_not_found",
                    "message": (
                        f"Ich habe keine passende Home-Assistant-Heizungs-Entity für {query} gefunden. "
                        "Ich kann sensor.* Temperaturwerte lesen, aber nicht darüber steuern."
                    ),
                }
            return {"resolved": False, "blocked": True, "reason": "entity_not_found", "message": "Ich habe keine passende Home-Assistant-Entity gefunden."}
        if len(candidates) > 1:
            if action == "set_temperature":
                return {
                    "resolved": False,
                    "ambiguous": True,
                    "candidates": candidates[:10],
                    "message": "Ich habe mehrere passende Heizungen gefunden.",
                }
            return {
                "resolved": False,
                "ambiguous": True,
                "candidates": candidates[:10],
                "message": "Ich habe mehrere passende Geräte gefunden.",
            }
        entity = candidates[0]
        prepared = self.prepare_control_action(str(entity["entity_id"]), action, parameters)
        return {"resolved": bool(prepared.get("prepared")), **prepared}

    def prepare_control_action(
        self,
        entity_id: str,
        action: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entity_id = str(entity_id).strip().lower()
        action = _canonical_action(action)
        domain = _domain(entity_id)
        if action not in SERVICE_MAP.get(domain, {}):
            return _blocked("action_not_supported", "Diese Aktion ist nicht in den festen Home-Assistant-Mappings enthalten.")
        validation = validate_control_request(entity_id, action)
        if validation.get("blocked"):
            return validation
        safe_parameters = _safe_parameters(action, parameters or {})
        auto = evaluate_auto_execution(entity_id, action, safe_parameters)
        if auto.get("blocked"):
            write_audit_log(
                "smart_home_auto_blocked",
                {"entity_id": entity_id, "domain": domain, "action": action, "reason": auto.get("reason")},
            )
            return auto
        title = _title(entity_id, action)
        requires_confirmation = bool(validation.get("requires_confirmation", True))
        if auto.get("auto_execute"):
            requires_confirmation = False
        return {
            "prepared": True,
            "provider": "home_assistant",
            "entity_id": entity_id,
            "domain": domain,
            "action": action,
            "parameters": safe_parameters,
            "risk": validation.get("risk", classify_action_risk(entity_id, domain, action)),
            "requires_confirmation": requires_confirmation,
            "auto_execute": bool(auto.get("auto_execute")),
            "auto_execute_reason": auto.get("reason"),
            "warning": validation.get("warning"),
            "title": title,
            "message": (
                f"Ich kann {title}. Auto-Ausführung gemäß Smart-Home-Policy."
                if auto.get("auto_execute")
                else auto.get("message") or f"Ich kann {title}. Diese Aktion benötigt Bestätigung."
            ),
        }

    def execute_control_action(
        self,
        entity_id: str,
        action: str,
        parameters: dict[str, Any] | None = None,
        source_command: str | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_control_action(entity_id, action, parameters)
        if prepared.get("blocked"):
            write_audit_log("ha_control_blocked", {"entity_id": entity_id, "action": action, "reason": prepared.get("reason")})
            return prepared
        settings = get_settings().require_home_assistant()
        assert settings.home_assistant_url is not None
        assert settings.home_assistant_token is not None
        domain = str(prepared["domain"])
        service = SERVICE_MAP[domain][str(prepared["action"])]
        payload = {"entity_id": prepared["entity_id"], **prepared.get("parameters", {})}
        url = f"{settings.home_assistant_url.rstrip('/')}/api/services/{domain}/{service}"
        write_audit_log("ha_control_start", {"entity_id": prepared["entity_id"], "action": prepared["action"], "risk": prepared["risk"]})
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {settings.home_assistant_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        write_audit_log("ha_control_end", {"entity_id": prepared["entity_id"], "action": prepared["action"], "status": "executed"})
        if prepared.get("auto_execute"):
            write_audit_log(
                "smart_home_auto_executed",
                {
                    "entity_id": prepared["entity_id"],
                    "friendly_name": _friendly_name(prepared["entity_id"]),
                    "domain": domain,
                    "action": prepared["action"],
                    "risk": prepared["risk"],
                    "reason": "trusted_auto_policy",
                    "source_command": source_command,
                },
            )
        return {
            "executed": True,
            "provider": "home_assistant",
            "entity_id": prepared["entity_id"],
            "domain": domain,
            "action": prepared["action"],
            "risk": prepared["risk"],
            "auto_execute": bool(prepared.get("auto_execute")),
            "title": prepared["title"],
            "parameters": prepared.get("parameters", {}),
            "message": f"{prepared['title']} wurde ausgeführt.",
        }

    def prepare_batch_action(self, domain: str, action: str) -> dict[str, Any]:
        domain = str(domain).lower()
        action = _canonical_action(action)
        max_size = _int_env("HA_CONTROL_MAX_BATCH_SIZE", 20)
        entities = self.catalog.list_entities(domain=domain, limit=500).get("entities", [])
        actions = []
        excluded = []
        for entity in entities:
            if len(actions) >= max_size:
                excluded.append({"entity_id": entity.get("entity_id"), "reason": "batch_limit"})
                continue
            prepared = self.prepare_control_action(str(entity.get("entity_id")), action)
            if prepared.get("prepared"):
                actions.append(prepared)
            else:
                excluded.append({"entity_id": entity.get("entity_id"), "reason": prepared.get("reason")})
        risk = "ORANGE" if any(item.get("risk") == "ORANGE" for item in actions) else "YELLOW"
        return {
            "prepared": bool(actions),
            "batch": True,
            "domain": domain,
            "action": action,
            "risk": risk,
            "requires_confirmation": True,
            "actions": actions,
            "excluded": excluded,
            "title": f"{len(actions)} {domain}-Entities {action}",
            "message": f"Ich kann {len(actions)} {domain}-Entities vorbereiten. Diese Aktion benötigt Bestätigung.",
        }

    def execute_batch_action(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        executed = []
        failed = []
        for item in actions[: _int_env("HA_CONTROL_MAX_BATCH_SIZE", 20)]:
            result = self.execute_control_action(str(item.get("entity_id")), str(item.get("action")), item.get("parameters") or {})
            if result.get("executed"):
                executed.append(result)
            else:
                failed.append(result)
        return {"executed": True, "count": len(executed), "results": executed, "failed": failed, "message": f"{len(executed)} Aktionen wurden ausgeführt."}

    def _find_entities(self, query: str, domain: str | None = None) -> list[dict[str, Any]]:
        normalized_query = _norm(query)
        policy = load_home_assistant_control_policy()
        override_matches = []
        for entity_id, override in policy.get("entity_overrides", {}).items():
            if domain and _domain(entity_id) != domain:
                continue
            if normalized_query in {_norm(entity_id), _norm(override.get("friendly_name", ""))}:
                override_matches.append({"entity_id": entity_id, "friendly_name": override.get("friendly_name"), "domain": _domain(entity_id), "is_allowlisted": True})
        if override_matches:
            return override_matches
        results = self.catalog.search_entities(query, domain=domain, limit=10).get("entities", [])
        exact = [item for item in results if _norm(item.get("friendly_name", "")) == normalized_query or _norm(item.get("entity_id", "")) == normalized_query]
        return exact or results


def _blocked(reason: str, message: str) -> dict[str, Any]:
    return {"blocked": True, "reason": reason, "message": message}


def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0].lower() if "." in entity_id else ""


def _norm(value: Any) -> str:
    return str(value).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def _canonical_action(action: str) -> str:
    normalized = _norm(action)
    mapping = {
        "ein": "turn_on",
        "an": "turn_on",
        "einschalten": "turn_on",
        "anschalten": "turn_on",
        "aktivieren": "turn_on",
        "starte": "turn_on",
        "aus": "turn_off",
        "ausschalten": "turn_off",
        "deaktivieren": "turn_off",
        "oeffnen": "open_cover",
        "öffnen": "open_cover",
        "schliessen": "close_cover",
        "schließen": "close_cover",
        "stoppen": "stop_cover",
    }
    return mapping.get(normalized, normalized)


def _action_from_command(command: str) -> str | None:
    normalized = _norm(command)
    if "grad" in normalized and ("temperatur" in normalized or "heizung" in normalized or re.search(r"\b\d+(?:[,.]\d+)?\s*grad\b", normalized)):
        return "set_temperature"
    if "rollladen" in normalized or "cover" in normalized:
        if "schliess" in normalized or "schlies" in normalized:
            return "close_cover"
        if "oeff" in normalized or "öff" in normalized:
            return "open_cover"
    if "einschalten" in normalized or " ein" in normalized or " an" in normalized or "licht an" in normalized or "aktiviere" in normalized:
        return "turn_on"
    if "ausschalten" in normalized or " aus" in normalized or "licht aus" in normalized or "deaktivieren" in normalized:
        return "turn_off"
    return None


def _target_from_command(command: str, action: str) -> str:
    cleaned = re.sub(r"^(jarvis|hey jarvis|ok jarvis|okay jarvis)[,\s:.-]*", "", command.strip(), flags=re.I)
    if action == "set_temperature":
        cleaned = re.sub(r"\b(stelle|setz(?:e)?|heizung|thermostat|temperatur|auf|\d+(?:[,.]\d+)?\s*grad)\b", " ", cleaned, flags=re.I)
        return re.sub(r"\s+", " ", cleaned).strip(" .!?:,") or cleaned
    for token in ("einschalten", "ausschalten", "anschalten", "mach", "schalte", "ein", "aus", "an"):
        cleaned = re.sub(rf"\b{token}\b", " ", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip(" .!?:,")


def _parameters_from_command(command: str, action: str | None) -> dict[str, Any]:
    if action != "set_temperature":
        return {}
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*grad", command, re.I)
    if not match:
        return {}
    return {"temperature": float(match.group(1).replace(",", "."))}


def _safe_parameters(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if action != "set_temperature":
        return {}
    try:
        return {"temperature": float(parameters["temperature"])}
    except (KeyError, TypeError, ValueError):
        return {}


def _title(entity_id: str, action: str) -> str:
    name = entity_id
    override = load_home_assistant_control_policy().get("entity_overrides", {}).get(entity_id, {})
    if isinstance(override, dict) and override.get("friendly_name"):
        name = str(override["friendly_name"])
    verbs = {
        "turn_on": "einschalten",
        "turn_off": "ausschalten",
        "toggle": "umschalten",
        "set_temperature": "Temperatur setzen",
        "open_cover": "öffnen",
        "close_cover": "schließen",
        "stop_cover": "stoppen",
    }
    return f"{name} {verbs.get(action, action)}"


def _friendly_name(entity_id: str) -> str:
    override = load_home_assistant_control_policy().get("entity_overrides", {}).get(entity_id, {})
    if isinstance(override, dict) and override.get("friendly_name"):
        return str(override["friendly_name"])
    for item in load_home_assistant_control_policy().get("trusted_switches", []):
        if isinstance(item, dict) and str(item.get("entity_id", "")).lower() == entity_id:
            return str(item.get("friendly_name") or entity_id)
    return entity_id


def _is_all_lights_command(command: str) -> bool:
    normalized = _norm(command)
    return "alle lichter" in normalized and (" aus" in normalized or " an" in normalized or "einschalten" in normalized or "ausschalten" in normalized)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
