import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.assistant.llm_client import LLMClient
from app.tools.files.content_extractors import clean_extracted_text, extract_text
from app.tools.files.path_safety import normalize_user_path


SUMMARY_MAX_CHARS = 12000
KEYWORDS = (
    "Kaufpreis",
    "Kaeufer",
    "Käufer",
    "Verkaeufer",
    "Verkäufer",
    "Objekt",
    "Grundbuch",
    "Notar",
    "UVZ",
    "Faelligkeit",
    "Fälligkeit",
    "Besitzuebergang",
    "Besitzübergang",
    "Auflassung",
    "Grundschuld",
)


class FileInspectTool:
    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def inspect_file(self, path: str, query: str | None = None) -> dict[str, Any]:
        resolved_result = _resolve_allowed(path)
        if resolved_result.get("blocked"):
            return resolved_result
        resolved = Path(resolved_result["path"])
        extracted = extract_text(resolved)
        stat = resolved.stat()
        success = not extracted.get("skipped") and not extracted.get("error")
        text = clean_extracted_text(str(extracted.get("text") or ""))
        return {
            "blocked": False,
            "filename": resolved.name,
            "path": str(resolved),
            "extension": resolved.suffix.lower(),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "text_preview": text[:1000],
            "extraction_success": success,
            "skipped_reason": extracted.get("reason"),
            "query": query,
        }

    def summarize_file(self, path: str, focus: str | None = None) -> dict[str, Any]:
        resolved_result = _resolve_allowed(path)
        if resolved_result.get("blocked"):
            return resolved_result
        resolved = Path(resolved_result["path"])
        extracted = extract_text(resolved)
        text = clean_extracted_text(str(extracted.get("text") or ""))[:SUMMARY_MAX_CHARS]
        if not text:
            return {"path": str(resolved), "summary": "Kein auswertbarer Text gefunden.", "used_llm": False}
        key_fields = self.extract_key_fields(str(resolved), document_type=focus)
        if self.llm_client.is_available():
            prompt = (
                "Fasse dieses Dokument sachlich zusammen. Nenne Unsicherheiten. "
                "Erfinde keine Daten."
            )
            if focus:
                prompt += f"\nFokus: {focus}"
            response = self.llm_client.create_response_with_tools(
                [{"role": "user", "content": f"{prompt}\n\n{text}"}],
                [],
            )
            summary = str(response.get("text") or "").strip()
            if summary:
                return {"path": str(resolved), "summary": summary, "used_llm": True, "key_fields": key_fields}
        return {
            "path": str(resolved),
            "summary": text[:1000],
            "used_llm": False,
            "key_fields": key_fields,
        }

    def extract_key_fields(self, path: str, document_type: str | None = None) -> dict[str, Any]:
        resolved_result = _resolve_allowed(path)
        if resolved_result.get("blocked"):
            return resolved_result
        resolved = Path(resolved_result["path"])
        extracted = extract_text(resolved)
        text = clean_extracted_text(str(extracted.get("text") or ""))
        key_snippets: dict[str, list[str]] = {}
        if (document_type or "").lower() in {"kaufvertrag", "vertrag"} or "kaufvertrag" in text.lower():
            for keyword in KEYWORDS:
                snippets = _keyword_snippets(text, keyword)
                if snippets:
                    canonical = _canonical_keyword(keyword)
                    key_snippets.setdefault(canonical, []).extend(snippets)
        return {
            "path": str(resolved),
            "document_type": document_type,
            "key_snippets": key_snippets,
            "message": "Eckdaten extrahiert." if key_snippets else "Keine Eckdaten gefunden.",
        }


def _resolve_allowed(path: str) -> dict[str, Any]:
    try:
        resolved = normalize_user_path(path)
    except ValueError:
        return {"blocked": True, "path": path, "message": "Datei liegt ausserhalb der erlaubten Verzeichnisse."}
    if not resolved.exists() or not resolved.is_file():
        return {"blocked": False, "path": str(resolved), "error": True, "message": "Datei wurde nicht gefunden."}
    return {"blocked": False, "path": str(resolved)}


def _keyword_snippets(text: str, keyword: str) -> list[str]:
    snippets: list[str] = []
    for match in re.finditer(re.escape(keyword), text, flags=re.I):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 120)
        snippets.append(text[start:end].strip())
        if len(snippets) >= 3:
            break
    return snippets


def _canonical_keyword(keyword: str) -> str:
    return {
        "Kaeufer": "Käufer",
        "Verkaeufer": "Verkäufer",
        "Faelligkeit": "Fälligkeit",
        "Besitzuebergang": "Besitzübergang",
    }.get(keyword, keyword)
