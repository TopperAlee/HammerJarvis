from __future__ import annotations

import re
from pathlib import Path

from hammer_jarvis.query.models import EngineeringQueryType, ParsedEngineeringQuery


_LIST_TYPES = {
    "alarme": "Alarm",
    "alarm": "Alarm",
    "variablen": "Variable",
    "variable": "Variable",
    "texte": "TextResource",
    "text": "TextResource",
    "dokumente": "Document",
    "dokument": "Document",
}


class EngineeringQueryParser:
    def parse(self, query: str) -> ParsedEngineeringQuery:
        normalized = _normalize(query)
        if not normalized:
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.UNKNOWN,
                message="Bitte eine Engineering-Frage eingeben.",
            )

        relationship_id = _relationship_id(query)
        if relationship_id:
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.EXPLAIN_RELATIONSHIP,
                relationship_id=relationship_id,
                search_text=relationship_id,
            )
        if _contains(normalized, "erklaere beziehung", "erklare beziehung", "erkläre beziehung"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.EXPLAIN_RELATIONSHIP,
                search_text=_tail(normalized, ("erklaere beziehung", "erklare beziehung", "erkläre beziehung")),
            )
        if _contains(normalized, "welche beziehungen hat", "zeige beziehungen", "beziehungen von"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.RELATIONSHIPS,
                search_text=_tail(normalized, ("welche beziehungen hat", "zeige beziehungen", "beziehungen von")),
            )
        if _contains(normalized, "wo wird", "verwendet", "nutzung von"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.USAGE,
                search_text=_usage_target(normalized),
            )
        if _contains(normalized, "welche diagnosen betreffen", "diagnosen zu", "diagnostics zu"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.DIAGNOSTICS,
                search_text=_tail(normalized, ("welche diagnosen betreffen", "diagnosen zu", "diagnostics zu")),
            )
        if _contains(normalized, "welche dokumente gehoeren zu", "welche dokumente gehören zu", "dokumente zu"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.DOCUMENTS,
                search_text=_tail(normalized, ("welche dokumente gehoeren zu", "welche dokumente gehören zu", "dokumente zu")),
            )
        if _contains(normalized, "zeige verwaiste objekte", "verwaiste objekte", "orphans"):
            return ParsedEngineeringQuery(query_type=EngineeringQueryType.ORPHANS)
        if _contains(normalized, "finde objekt", "suche objekt"):
            return ParsedEngineeringQuery(
                query_type=EngineeringQueryType.OBJECT_SEARCH,
                search_text=_tail(normalized, ("finde objekt", "suche objekt")),
            )
        for phrase, object_type in _LIST_TYPES.items():
            if f"zeige alle {phrase}" in normalized or f"liste alle {phrase}" in normalized:
                return ParsedEngineeringQuery(
                    query_type=EngineeringQueryType.LIST_OBJECT_TYPE,
                    object_type=object_type,
                    search_text=phrase,
                )

        return ParsedEngineeringQuery(
            query_type=EngineeringQueryType.UNKNOWN,
            search_text=normalized,
            message="Ich kann diese Engineering-Frage noch nicht regelbasiert auswerten.",
        )


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split()).strip(" ?!.")


def _contains(value: str, *phrases: str) -> bool:
    return any(phrase in value for phrase in phrases)


def _tail(value: str, phrases: tuple[str, ...]) -> str:
    for phrase in phrases:
        if phrase in value:
            return value.split(phrase, 1)[1].strip(" :?!.")
    return value


def _usage_target(value: str) -> str:
    if value.startswith("wo wird "):
        return value.removeprefix("wo wird ").replace(" verwendet", "").strip(" ?!.")
    if " verwendet" in value:
        return value.replace(" verwendet", "").strip(" ?!.")
    return _tail(value, ("nutzung von",))


def _relationship_id(query: str) -> str | None:
    match = re.search(r"(relationship:[A-Za-z0-9_-]+)", query)
    if match:
        return match.group(1)
    if query.startswith("relationship:"):
        return Path(query).name
    return None
