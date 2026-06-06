import os
import re
from typing import Any
from urllib.parse import urlparse

from app.tools.web.page_fetcher import PageFetcher
from app.tools.web.searxng_client import SearxngClient


DISABLED_MESSAGE = "Internetrecherche ist noch nicht aktiviert. Setze WEB_RESEARCH_ENABLED=true und SEARXNG_BASE_URL."
OFFICIAL_DOCUMENTATION_DOMAINS = {
    "learn.microsoft.com",
    "docs.python.org",
    "developers.google.com",
    "docs.github.com",
    "docs.docker.com",
    "docs.ollama.com",
    "docs.searxng.org",
}
BOILERPLATE_PHRASES = (
    "Zu Hauptinhalt wechseln",
    "Skip to main content",
    "Dieser Browser wird nicht mehr unterstützt",
    "Dieser Browser wird nicht mehr unterstuetzt",
    "This browser is no longer supported",
    "Upgrade to Microsoft Edge",
    "Zur Ask Learn-Chaterfahrung wechseln",
)


class WebResearchTool:
    def __init__(
        self,
        client: SearxngClient | None = None,
        fetcher: PageFetcher | None = None,
    ) -> None:
        self.client = client or SearxngClient()
        self.fetcher = fetcher or PageFetcher()

    def status(self) -> dict[str, Any]:
        return get_web_research_status()

    def search_web(self, query: str) -> dict[str, Any]:
        if not _is_enabled():
            return {"error": True, "enabled": False, "query": query, "results": [], "message": DISABLED_MESSAGE}
        refined_query = refine_web_query(query)
        result = self.client.search(refined_query, max_results=_max_results())
        if result.get("results"):
            result["results"] = rank_search_results(result["results"], query)
        result["original_query"] = query
        return result

    def research(self, query: str) -> dict[str, Any]:
        if not _is_enabled():
            return {
                "error": True,
                "enabled": False,
                "query": query,
                "sources": [],
                "summary": "",
                "message": DISABLED_MESSAGE,
            }
        search_result = self.search_web(query)
        if search_result.get("error"):
            return {**search_result, "sources": [], "summary": ""}

        sources: list[dict[str, Any]] = []
        bullet_points: list[str] = []
        for result in rank_search_results(search_result.get("results", []), query)[:_max_results()]:
            fetched = self.fetcher.fetch_text(str(result.get("url", "")))
            preview = clean_web_text(str(fetched.get("text") or result.get("content") or "").strip())
            domain = _domain_from_url(str(result.get("url", "")))
            quality = classify_source_quality(domain, result)
            sources.append(
                {
                    "title": result.get("title", "Ohne Titel"),
                    "url": result.get("url", ""),
                    "source": result.get("source", domain),
                    "domain": domain,
                    "source_quality": quality,
                    "snippet": preview[:300],
                    "text_preview": preview[:300],
                    "fetched": bool(fetched.get("fetched")),
                    "relevance_reason": _relevance_reason(quality, domain),
                }
            )
            if preview:
                bullet_points.append(_sentence_preview(preview))

        if not bullet_points and sources:
            bullet_points = ["Es wurden Quellen gefunden, aber keine auswertbare Textvorschau geladen."]
        return {
            "query": query,
            "search_query": search_result.get("query", query),
            "provider": search_result.get("provider", "searxng"),
            "sources": sources,
            "source_count": len(sources),
            "summary": " ".join(bullet_points[:3]).strip(),
            "summary_points": bullet_points[:4],
            "confidence": _confidence_for_sources(sources),
            "limitations": _limitations_for_sources(sources),
            "message": f"{len(sources)} Quellen ausgewertet.",
        }


def get_web_research_status() -> dict[str, Any]:
    return {
        "enabled": _is_enabled(),
        "provider": os.getenv("WEB_SEARCH_PROVIDER", "searxng"),
        "searxng_base_url": os.getenv("SEARXNG_BASE_URL", "http://localhost:8080"),
        "max_results": _max_results(),
        "fetch_timeout_seconds": int(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15")),
    }


def format_web_research_answer(result: dict[str, Any]) -> str:
    if result.get("enabled") is False or result.get("error") and not result.get("sources"):
        return str(result.get("message") or DISABLED_MESSAGE)
    if not result.get("sources"):
        return "Ich habe online recherchiert.\nEs wurden keine verlaesslichen Quellen gefunden."

    lines = ["Ich habe online recherchiert.", "", "Kurzfassung:"]
    summary_points = result.get("summary_points") or []
    if not summary_points and result.get("summary"):
        summary_points = [result["summary"]]
    for point in summary_points[:4]:
        lines.append(f"- {clean_web_text(str(point))}")

    lines.extend(["", "Beste Quellen:"])
    for index, source in enumerate(result.get("sources", [])[:5], start=1):
        title = source.get("title") or source.get("source") or "Quelle"
        url = source.get("url") or ""
        lines.append(f"{index}. {title} - {url}")
        lines.append(f"   Warum relevant: {source.get('relevance_reason', 'Passendes Suchergebnis.')}")

    lines.extend(["", "Einordnung:"])
    lines.append(f"- confidence: {result.get('confidence', 'niedrig')}")
    limitations = str(result.get("limitations") or "").strip()
    if limitations:
        lines.append(f"- limitations: {limitations}")
    return "\n".join(lines)


def clean_web_text(text: str) -> str:
    cleaned = text
    for phrase in BOILERPLATE_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = re.sub(r"\b(Contents|Navigation|Feedback|In this article)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:300].strip()


def refine_web_query(query: str) -> str:
    original = query.strip()
    lowered = original.lower()
    topic = original
    for phrase in (
        "offizielle dokumentation zu",
        "offizielle dokumentation für",
        "offizielle dokumentation fuer",
        "official documentation for",
        "official documentation",
    ):
        topic = re.sub(phrase, "", topic, flags=re.I).strip()
    if any(term in lowered for term in ("offizielle dokumentation", "official documentation")):
        if any(term in lowered for term in ("microsoft", "graph")):
            return f"{topic} official documentation site:learn.microsoft.com"
        return f"{topic} official documentation".strip()
    return original


def rank_search_results(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return sorted(results, key=lambda item: _ranking_score(item, query), reverse=True)


def classify_source_quality(domain: str, result: dict[str, Any] | None = None) -> str:
    lowered_domain = domain.lower()
    if lowered_domain in OFFICIAL_DOCUMENTATION_DOMAINS:
        return "official"
    if "docs." in lowered_domain or "documentation" in lowered_domain:
        return "documentation"
    combined = f"{lowered_domain} {result or {}}".lower()
    if any(term in combined for term in ("blog", "medium.com", "substack", "dev.to")):
        return "blog"
    if any(term in combined for term in ("news", "heise", "zdnet", "theverge")):
        return "news"
    return "unknown"


def _ranking_score(result: dict[str, Any], query: str) -> int:
    domain = _domain_from_url(str(result.get("url", "")))
    quality = classify_source_quality(domain, result)
    score = {"official": 100, "documentation": 70, "unknown": 30, "news": 20, "blog": 10}.get(quality, 0)
    lowered_query = query.lower()
    if "graph" in lowered_query and domain == "learn.microsoft.com":
        score += 80
    if "microsoft" in lowered_query and domain == "learn.microsoft.com":
        score += 50
    return score


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _sentence_preview(text: str) -> str:
    cleaned = clean_web_text(text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return (parts[0] if parts and parts[0] else cleaned).strip()


def _relevance_reason(quality: str, domain: str) -> str:
    if quality == "official":
        return f"Offizielle Dokumentationsquelle ({domain})."
    if quality == "documentation":
        return f"Dokumentationsquelle ({domain})."
    if quality == "blog":
        return f"Ergaenzende Blogquelle ({domain})."
    return f"Passendes Suchergebnis ({domain})."


def _confidence_for_sources(sources: list[dict[str, Any]]) -> str:
    if any(source.get("source_quality") == "official" for source in sources):
        return "hoch"
    if any(source.get("source_quality") in {"documentation", "unknown"} for source in sources):
        return "mittel"
    return "niedrig"


def _limitations_for_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "Keine Quellen gefunden."
    if any(source.get("source_quality") == "official" for source in sources):
        return "Antwort basiert auf den gefundenen Quellen; Details sollten in der offiziellen Dokumentation geprueft werden."
    return "Es wurden keine offiziellen Dokumentationsquellen gefunden; Ergebnis nur als Orientierung verwenden."


def _is_enabled() -> bool:
    return os.getenv("WEB_RESEARCH_ENABLED", "false").strip().lower() == "true"


def _max_results() -> int:
    return int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
