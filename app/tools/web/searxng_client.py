import os
from typing import Any
from urllib.parse import urlparse

import httpx


class SearxngClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")).rstrip("/")

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        try:
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
        return {
            "query": query,
            "provider": "searxng",
            "results": results,
            "message": f"{len(results)} Suchergebnisse gefunden.",
        }


def _source_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url
