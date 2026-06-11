import json
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).with_name("home_assistant_control_policy.json")
SAFE_FALLBACK_POLICY: dict[str, Any] = {
    "control_mode": "disabled",
    "require_confirmation_for_all_actions": True,
    "auto_execute_enabled": False,
    "auto_execute_domains": {},
    "require_confirmation_domains": [],
    "trusted_switches": [],
    "enable_high_risk_actions": False,
    "require_pin_for_high_risk": True,
    "confirmation_pin_hash": "",
    "default_action_expiry_minutes": 10,
    "domains": {},
    "entity_overrides": {},
    "blocked_entities": [],
    "blocked_domains": [],
}


def load_home_assistant_control_policy() -> dict[str, Any]:
    """Load the local control policy; invalid config fails closed with no writes enabled."""
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return dict(SAFE_FALLBACK_POLICY)
    if not isinstance(data, dict):
        return dict(SAFE_FALLBACK_POLICY)
    return {
        **SAFE_FALLBACK_POLICY,
        **data,
        "domains": data.get("domains") if isinstance(data.get("domains"), dict) else {},
        "auto_execute_domains": data.get("auto_execute_domains") if isinstance(data.get("auto_execute_domains"), dict) else {},
        "entity_overrides": data.get("entity_overrides") if isinstance(data.get("entity_overrides"), dict) else {},
        "blocked_entities": _string_list(data.get("blocked_entities")),
        "blocked_domains": _string_list(data.get("blocked_domains")),
        "require_confirmation_domains": _string_list(data.get("require_confirmation_domains")),
        "trusted_switches": data.get("trusted_switches") if isinstance(data.get("trusted_switches"), list) else [],
    }


def save_control_policy(policy: dict[str, Any]) -> dict[str, Any]:
    POLICY_PATH.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return load_home_assistant_control_policy()


def get_domain_policy(domain: str) -> dict[str, Any]:
    policy = load_home_assistant_control_policy()
    domains = policy.get("domains", {})
    item = domains.get(str(domain).lower()) if isinstance(domains, dict) else None
    return item if isinstance(item, dict) else {"enabled": False, "risk": "BLOCKED", "allowed_actions": []}


def get_entity_override(entity_id: str) -> dict[str, Any] | None:
    overrides = load_home_assistant_control_policy().get("entity_overrides", {})
    item = overrides.get(str(entity_id).lower()) if isinstance(overrides, dict) else None
    return item if isinstance(item, dict) else None


def get_trusted_switch(entity_id: str) -> dict[str, Any] | None:
    entity_id = str(entity_id).lower()
    for item in load_home_assistant_control_policy().get("trusted_switches", []):
        if isinstance(item, dict) and str(item.get("entity_id", "")).lower() == entity_id:
            return item
    return None


def is_domain_enabled(domain: str) -> bool:
    policy = load_home_assistant_control_policy()
    if str(domain).lower() in set(policy.get("blocked_domains", [])):
        return False
    return bool(get_domain_policy(domain).get("enabled"))


def is_action_supported(domain: str, action: str) -> bool:
    domain_policy = get_domain_policy(domain)
    return str(action) in {str(item) for item in domain_policy.get("allowed_actions", [])}


def classify_action_risk(entity_id: str, domain: str, action: str) -> str:
    override = get_entity_override(entity_id)
    if override and action in override.get("allowed_actions", []):
        return str(override.get("risk", get_domain_policy(domain).get("risk", "RED"))).upper()
    return str(get_domain_policy(domain).get("risk", "RED")).upper()


def is_entity_blocked(entity_id: str) -> bool:
    entity_id = str(entity_id).lower()
    return entity_id in {str(item).lower() for item in load_home_assistant_control_policy().get("blocked_entities", [])}


def validate_control_request(entity_id: str, action: str) -> dict[str, Any]:
    entity_id = str(entity_id).strip().lower()
    action = str(action).strip()
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    policy = load_home_assistant_control_policy()
    override = get_entity_override(entity_id)
    if is_entity_blocked(entity_id):
        return _blocked("entity_blocked", "Diese Entity ist in der Control Policy blockiert.")
    if domain in set(policy.get("blocked_domains", [])):
        return _blocked("domain_blocked", "Diese Home-Assistant-Domain ist blockiert.")
    if override:
        if not override.get("enabled", False):
            return _blocked("entity_disabled", "Diese Entity ist in der Control Policy deaktiviert.")
        if action not in override.get("allowed_actions", []):
            return _blocked("action_not_supported", "Diese Aktion ist für diese Entity nicht freigegeben.")
        return _allowed(entity_id, domain, action, str(override.get("risk", "YELLOW")).upper(), override.get("warning"))
    domain_policy = get_domain_policy(domain)
    if not domain_policy.get("enabled", False):
        return _blocked("domain_disabled", "Diese Home-Assistant-Domain ist nicht für Steuerung aktiviert.")
    if action not in domain_policy.get("allowed_actions", []):
        return _blocked("action_not_supported", "Diese Aktion ist für diese Domain nicht freigegeben.")
    risk = str(domain_policy.get("risk", "RED")).upper()
    if risk == "RED" and not policy.get("enable_high_risk_actions", False):
        return _blocked("red_blocked", "Rote Home-Assistant-Aktionen sind deaktiviert.")
    if risk == "RED" and policy.get("require_pin_for_high_risk", True) and not policy.get("confirmation_pin_hash"):
        return _blocked("pin_not_configured", "Rote Aktionen bleiben blockiert, weil keine PIN konfiguriert ist.")
    return _allowed(entity_id, domain, action, risk, domain_policy.get("warning"))


def evaluate_auto_execution(
    entity_id: str,
    action: str,
    parameters: dict[str, Any] | None = None,
    current_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether a validated control action may bypass a confirmation prompt.

    This is intentionally policy-only: it never creates service names or payloads.
    The broker still validates against explicit domain/action mappings before
    executing anything.
    """
    entity_id = str(entity_id).strip().lower()
    action = str(action).strip()
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    policy = load_home_assistant_control_policy()
    if not policy.get("auto_execute_enabled") or policy.get("control_mode") != "trusted_auto":
        return {"auto_execute": False, "reason": "auto_execute_disabled"}
    if domain in set(policy.get("blocked_domains", [])):
        return {"auto_execute": False, "blocked": True, "reason": "domain_blocked", "message": "Nicht ausgeführt: Diese Geräteklasse ist blockiert."}
    if domain in set(policy.get("require_confirmation_domains", [])):
        return {"auto_execute": False, "reason": "confirmation_required_domain"}
    domain_policy = policy.get("auto_execute_domains", {}).get(domain, {})
    if not isinstance(domain_policy, dict) or not domain_policy.get("enabled"):
        return {"auto_execute": False, "reason": "domain_not_auto_enabled"}
    if action not in {str(item) for item in domain_policy.get("actions", [])}:
        return {"auto_execute": False, "reason": "action_not_auto_enabled"}
    if domain == "light":
        return {"auto_execute": True, "reason": "trusted_auto_policy"}
    if domain == "switch":
        trusted = get_trusted_switch(entity_id)
        override = get_entity_override(entity_id) or {}
        category = str((trusted or override).get("category", "")).lower() if isinstance((trusted or override), dict) else ""
        if trusted and trusted.get("auto_execute"):
            return {"auto_execute": True, "reason": "trusted_auto_policy"}
        if override.get("auto_execute") and category in {"smart_plug", "light_equivalent"}:
            return {"auto_execute": True, "reason": "trusted_auto_policy"}
        if category in {"smart_plug", "light_equivalent"} and not domain_policy.get("only_if_trusted_switch", True):
            return {"auto_execute": True, "reason": "trusted_auto_policy"}
        return {
            "auto_execute": False,
            "reason": "switch_not_trusted",
            "message": "Nicht automatisch ausgeführt: Dieser Switch ist noch nicht als sichere Smartsteckdose freigegeben.",
        }
    if domain == "climate":
        if action != "set_temperature":
            return {"auto_execute": False, "reason": "climate_action_not_auto_enabled"}
        try:
            temperature = float((parameters or {})["temperature"])
        except (KeyError, TypeError, ValueError):
            return {"auto_execute": False, "blocked": True, "reason": "temperature_missing", "message": "Nicht ausgeführt: Ich habe keine gültige Temperatur erkannt."}
        min_temp = float(domain_policy.get("temperature_min", 16))
        max_temp = float(domain_policy.get("temperature_max", 24))
        if temperature < min_temp or temperature > max_temp:
            return {
                "auto_execute": False,
                "blocked": True,
                "reason": "temperature_out_of_range",
                "message": f"Nicht ausgeführt: {temperature:g} °C liegt außerhalb der erlaubten Auto-Grenze von {min_temp:g}–{max_temp:g} °C.",
            }
        current = _current_temperature(current_state)
        max_delta = float(domain_policy.get("max_delta_celsius", 3))
        if current is not None and abs(temperature - current) > max_delta:
            return {
                "auto_execute": False,
                "blocked": True,
                "reason": "temperature_delta_too_large",
                "message": f"Nicht ausgeführt: Die Änderung überschreitet die erlaubte Auto-Grenze von {max_delta:g} °C.",
            }
        return {"auto_execute": True, "reason": "trusted_auto_policy"}
    return {"auto_execute": False, "reason": "domain_not_auto_supported"}


def _allowed(entity_id: str, domain: str, action: str, risk: str, warning: Any = None) -> dict[str, Any]:
    return {
        "allowed": True,
        "entity_id": entity_id,
        "domain": domain,
        "action": action,
        "risk": risk,
        "warning": warning,
        "requires_confirmation": risk != "GREEN",
    }


def _blocked(reason: str, message: str) -> dict[str, Any]:
    return {"allowed": False, "blocked": True, "reason": reason, "message": message}


def _current_temperature(current_state: dict[str, Any] | None) -> float | None:
    if not isinstance(current_state, dict):
        return None
    attributes = current_state.get("attributes") or current_state.get("attributes_summary") or {}
    if not isinstance(attributes, dict):
        return None
    for key in ("current_temperature", "temperature"):
        try:
            return float(attributes[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _string_list(value: Any) -> list[str]:
    return [str(item).lower() for item in value] if isinstance(value, list) else []
