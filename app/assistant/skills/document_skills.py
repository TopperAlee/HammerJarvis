import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.tool_registry import ToolRegistry


KAUFVERTRAG_FIELDS = {
    "dokumenttyp": ("Kaufvertrag", "Dokumenttyp"),
    "datum": ("Datum",),
    "uvz": ("UVZ", "Urkundenzeichen"),
    "kaeufer": ("Käufer", "Kaeufer"),
    "verkaeufer": ("Verkäufer", "Verkaeufer"),
    "objekt_adresse": ("Objekt", "Adresse"),
    "kaufpreis": ("Kaufpreis",),
    "faelligkeit": ("Fälligkeit", "Faelligkeit"),
    "besitzuebergang": ("Besitzübergang", "Besitzuebergang"),
    "grundbuch": ("Grundbuch",),
    "notar": ("Notar",),
    "risiken_offene_punkte": ("Risiken", "offene Punkte", "Grundschuld", "Auflassung"),
}


@dataclass(frozen=True)
class SkillDefinition:
    """Metadata for one user-facing high-level skill."""

    name: str
    description: str
    risk: ActionRisk
    required_tools: list[str]
    executor: Any


class DocumentSummarySkill:
    """Summarize a local allowed document without exposing content externally."""

    name = "document_summarize"
    description = "Fasst eine erlaubte lokale Datei zusammen."
    risk = ActionRisk.GREEN
    required_tools = ["file_summarize"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run the registered file summarizer and normalize its response."""
        path = str(input_data.get("path") or "")
        focus = input_data.get("focus")
        executed = self.tool_registry.execute_tool(
            "file_summarize",
            {"path": path, "focus": focus},
        )
        result = executed.get("result", executed)
        if result.get("blocked"):
            return _blocked_response(self.name, path)
        return {
            "skill": self.name,
            "risk": self.risk,
            "summary": str(result.get("summary") or "Keine Zusammenfassung verfügbar."),
            "file": _file_info(result),
            "limitations": _summary_limitations(result),
            "result": result,
        }


class KeyFieldExtractionSkill:
    """Extract key fields from an allowed local document without inventing values."""

    name = "document_extract_key_fields"
    description = "Extrahiert Eckdaten aus einer erlaubten lokalen Datei."
    risk = ActionRisk.GREEN
    required_tools = ["file_extract_key_fields"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Extract deterministic snippets and map missing fields to 'nicht gefunden'."""
        path = str(input_data.get("path") or "")
        document_type = str(input_data.get("document_type") or "unknown")
        executed = self.tool_registry.execute_tool(
            "file_extract_key_fields",
            {"path": path, "document_type": document_type},
        )
        result = executed.get("result", executed)
        if result.get("blocked"):
            return _blocked_response(self.name, path)

        snippets = _normalize_snippet_map(result.get("key_snippets", {}))
        fields = _fields_from_snippets(snippets, document_type)
        return {
            "skill": self.name,
            "risk": self.risk,
            "document_type": document_type,
            "fields": fields,
            "file": _file_info(result),
            "result": result,
        }


def _blocked_response(skill: str, path: str) -> dict[str, Any]:
    return {
        "skill": skill,
        "risk": ActionRisk.GREEN,
        "blocked": True,
        "path": path,
        "message": "Datei liegt ausserhalb der erlaubten Verzeichnisse.",
    }


def _file_info(result: dict[str, Any]) -> dict[str, Any]:
    path = str(result.get("path") or "")
    return {
        "path": path,
        "filename": Path(path).name if path else "",
    }


def _summary_limitations(result: dict[str, Any]) -> list[str]:
    limitations = ["Nur lokale Dateien aus erlaubten Verzeichnissen werden verarbeitet."]
    if not result.get("used_llm"):
        limitations.append("Kein lokales LLM genutzt; Antwort basiert auf extrahiertem Text.")
    return limitations


def _normalize_snippet_map(raw: Any) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return normalized
    for key, values in raw.items():
        canonical = _canonical_key(str(key))
        normalized.setdefault(canonical, [])
        if isinstance(values, list):
            normalized[canonical].extend(str(value) for value in values)
        elif values:
            normalized[canonical].append(str(values))
    return normalized


def _fields_from_snippets(snippets: dict[str, list[str]], document_type: str) -> dict[str, dict[str, str]]:
    keys = KAUFVERTRAG_FIELDS if document_type.lower() == "kaufvertrag" else KAUFVERTRAG_FIELDS
    fields: dict[str, dict[str, str]] = {}
    for field_key, aliases in keys.items():
        snippet = _first_matching_snippet(snippets, aliases)
        if not snippet:
            fields[field_key] = {"value": "nicht gefunden", "confidence": "low", "snippet": ""}
            continue
        fields[field_key] = {
            "value": _extract_value(field_key, snippet),
            "confidence": "medium",
            "snippet": snippet,
        }
    return fields


def _first_matching_snippet(snippets: dict[str, list[str]], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        canonical = _canonical_key(alias)
        if snippets.get(canonical):
            return snippets[canonical][0]
    for values in snippets.values():
        for snippet in values:
            lowered = snippet.lower()
            if any(alias.lower() in lowered for alias in aliases):
                return snippet
    return ""


def _canonical_key(value: str) -> str:
    lowered = value.lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ã¤": "ae",
        "Ã¶": "oe",
        "Ã¼": "ue",
    }
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def _extract_value(field_key: str, snippet: str) -> str:
    if field_key == "uvz":
        match = re.search(r"\bUVZ\b\s*[:#/ -]*\s*([A-Za-z0-9./-]+)?", snippet, flags=re.I)
        if match and match.group(1):
            return f"UVZ {match.group(1)}"
    return snippet[:180].strip() or "nicht gefunden"
