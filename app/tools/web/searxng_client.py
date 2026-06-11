import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from app.assistant.performance.timing import time_operation

_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class SearxngClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")).rstrip("/")

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        cache_key = f"{query}|{max_results}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return {**cached, "source": "cache"}
        try:
            with time_operation("web_search.searxng", "web"):
                response = httpx.get(
                    f"{self.base_url}/search",
                    params={"q": query, "format": "json"},
                    timeout=float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15")),
                )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {
                "error": True,
                "provider": "searxng",
                "query": query,
                "results": [],
                "message": "Websuche ist nicht erreichbar. Bitte SearXNG konfigurieren oder starten.",
            }

        results = []
        for item in payload.get("results", [])[:max_results]:
            url = str(item.get("url") or "")
            results.append(
                {
                    "title": str(item.get("title") or url or "Ohne Titel"),
                    "url": url,
                    "content": str(item.get("content") or item.get("snippet") or ""),
                    "source": _source_from_url(url),
                }
            )
        result = {
            "query": query,
            "provider": "searxng",
            "results": results,
            "message": f"{len(results)} Suchergebnisse gefunden.",
        }
        _set_cached(cache_key, result)
        return result


def _source_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _get_cached(key: str) -> dict[str, Any] | None:
    if os.getenv("WEB_SEARCH_CACHE_ENABLED", "true").strip().lower() != "true":
        return None
    cached = _SEARCH_CACHE.get(key)
    if not cached:
        return None
    timestamp, data = cached
    ttl = float(os.getenv("WEB_SEARCH_CACHE_TTL_SECONDS", "300"))
    if time.time() - timestamp > ttl:
        _SEARCH_CACHE.pop(key, None)
        return None
    return dict(data)


def _set_cached(key: str, data: dict[str, Any]) -> None:
    if os.getenv("WEB_SEARCH_CACHE_ENABLED", "true").strip().lower() != "true":
        return
    _SEARCH_CACHE[key] = (time.time(), dict(data))
