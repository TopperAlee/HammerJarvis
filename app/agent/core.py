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
        text = message.strip()
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
                "was macht ecoflow gerade",
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

        search_query = _extract_search_query(text)
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

        write_audit_log("chat_fallback", {"message_length": len(message)})
        return {"intent": "fallback", "message": FALLBACK_MESSAGE}


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
    details = human_status.get("details", [])
    if details:
        return f"{human_status.get('headline', '')} {'; '.join(details)}"
    return str(human_status.get("headline", overview.get("summary", "")))
