import re
from typing import Any

from app.agent.permissions import classify_action
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant import HomeAssistantTool


FALLBACK_MESSAGE = (
    "Ich habe dich verstanden, aber fuer diesen Befehl gibt es in v0.1 noch kein Werkzeug."
)


class HammerJarvisCore:
    def __init__(self, ha_tool: HomeAssistantTool | None = None) -> None:
        self.ha_tool = ha_tool or HomeAssistantTool()

    def handle_message(self, message: str) -> dict[str, Any]:
        original_text = message.strip()
        text = normalize_message(message)
        display_text = normalize_message(message, lowercase=False)
        normalized = _normalize(text)

        switch_match = re.search(r"schalte\s+([a-zA-Z0-9_.]+)\s+(ein|aus)", text, re.I)
        if switch_match:
            action = "turn_on" if switch_match.group(2).lower() == "ein" else "turn_off"
            risk = classify_action(action)
            entity_id = switch_match.group(1)
            write_audit_log(
                "chat_confirmation_required",
                {"action": action, "entity_id": entity_id, "risk": risk},
            )
            return {
                "intent": "ha_switch",
                "confirmation_required": True,
                "action": action,
                "entity_id": entity_id,
                "risk": risk,
            }

        if any(
            term in normalized
            for term in (
                "energieuebersicht",
                "energieubersicht",
                "ecoflow energie",
                "wie viel solarstrom",
                "wie voll ist die batterie",
                "wie ist der batteriestand",
                "was macht ecoflow gerade",
                "solar status",
                "energie status",
            )
        ):
            overview = self.ha_tool.get_ecoflow_energy_overview()
            write_audit_log(
                "chat_ha_ecoflow_energy",
                {
                    "has_pv_power": overview["pv_power_w"] is not None,
                    "has_soc": overview["soc_percent"] is not None,
                },
            )
            return {
                "intent": "ha_ecoflow_energy",
                "message": _format_human_status_message(overview),
                "overview": overview,
            }

        if any(
            term in normalized
            for term in (
                "ecoflow diagnose",
                "zeige ecoflow",
                "was ist mit ecoflow",
                "ecoflow werte",
                "smartmeter werte",
            )
        ):
            diagnostic = self.ha_tool.diagnose_ecoflow()
            write_audit_log(
                "chat_ha_ecoflow",
                {
                    "total": diagnostic["total"],
                    "unavailable_count": diagnostic["unavailable_count"],
                    "unknown_count": diagnostic["unknown_count"],
                },
            )
            return {
                "intent": "ha_ecoflow",
                "message": diagnostic["summary"],
                "diagnostic": diagnostic,
            }

        if any(
            term in normalized
            for term in (
                "geraete haben probleme",
                "gerate haben probleme",
                "zeige probleme",
                "home assistant diagnose",
                "was ist offline",
            )
        ):
            problems = self.ha_tool.get_problem_entities()
            write_audit_log(
                "chat_ha_problems",
                {
                    "critical_count": problems["critical_count"],
                    "warning_count": problems["warning_count"],
                    "informational_count": problems["informational_count"],
                },
            )
            return {"intent": "ha_problems", "problems": problems}

        if any(term in normalized for term in ("nicht verfuegbar", "unavailable", "unknown")):
            entities = self.ha_tool.get_unavailable_entities()
            write_audit_log("chat_ha_unavailable", {"count": len(entities)})
            return {"intent": "ha_unavailable", "entities": entities}

        if "wie viele entities" in normalized or "zeige alle entities" in normalized:
            entities = self.ha_tool.get_all_states()
            write_audit_log("chat_ha_entities", {"count": len(entities)})
            return {
                "intent": "ha_entities_count",
                "count": len(entities),
                "entities": entities,
            }

        search_query = _extract_search_query(display_text)
        if search_query:
            entities = self.ha_tool.search_entities(search_query)
            write_audit_log(
                "chat_ha_search", {"query": search_query, "count": len(entities)}
            )
            return {"intent": "ha_search", "query": search_query, "entities": entities}

        if any(
            term in normalized
            for term in (
                "energie werte",
                "stromverbrauch",
                "watt sensoren",
            )
        ):
            entities = self.ha_tool.get_power_entities()
            write_audit_log("chat_ha_power", {"count": len(entities)})
            return {"intent": "ha_power", "entities": entities}

        write_audit_log("chat_fallback", {"message_length": len(original_text)})
        return {"intent": "fallback", "message": FALLBACK_MESSAGE}


def normalize_message(message: str, lowercase: bool = True) -> str:
    normalized = re.sub(r"\s+", " ", message.strip())
    if lowercase:
        normalized = normalized.lower()
    wake_pattern = (
        r"^(?:hey\s+jarvis|okay\s+jarvis|ok\s+jarvis|hallo\s+jarvis|"
        r"hammer\s+jarvis|jarvis)\s*[,:\-]?\s*"
    )
    normalized = re.sub(wake_pattern, "", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize(value: str) -> str:
    return (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .replace("Ã¤", "ae")
        .replace("Ã¶", "oe")
        .replace("Ã¼", "ue")
        .replace("ÃŸ", "ss")
    )


def _extract_search_query(message: str) -> str | None:
    match = re.match(r"\s*(suche|finde|search)\s+(.+?)\s*$", message, re.I)
    if not match:
        return None
    query = match.group(2).strip()
    return query or None


def _format_human_status_message(overview: dict[str, Any]) -> str:
    human_status = overview.get("human_status")
    if not human_status:
        return str(overview.get("summary", ""))
    lines: list[str] = []
    headline = str(human_status.get("headline", "")).strip()
    if headline:
        lines.append(headline)
    details = human_status.get("details", [])
    if details:
        lines.extend(f"- {detail}" for detail in details)
    warnings = overview.get("warnings", [])
    warning_messages = [
        str(warning.get("message", "")).strip()
        for warning in warnings
        if warning.get("message")
    ][:3]
    if warning_messages:
        lines.append("Hinweise:")
        lines.extend(f"- {message}" for message in warning_messages)
    return "\n".join(lines) if lines else str(overview.get("summary", ""))
