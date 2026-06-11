import os
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from app.assistant.performance.timing import time_operation


TEXT_PREVIEW_CHARS = 5000


class PageFetcher:
    def fetch_text(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return {"url": url, "fetched": False, "error": True, "message": "Nur http/https URLs sind erlaubt."}
        try:
            with time_operation("web_fetch.page", "web"):
                response = httpx.get(
                    url,
                    follow_redirects=True,
                    timeout=float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15")),
                )
            response.raise_for_status()
        except Exception:
            return {"url": url, "fetched": False, "error": True, "message": "Seite konnte nicht geladen werden."}

        content_type = response.headers.get("content-type", "").lower()
        if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml")):
            return {"url": url, "fetched": False, "error": True, "message": "Binaere oder unsichere Datei wurde nicht geladen."}
        content = response.content[: int(os.getenv("WEB_FETCH_MAX_BYTES", "500000"))]
        soup = BeautifulSoup(content, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        text = " ".join(soup.get_text(" ").split())[:TEXT_PREVIEW_CHARS]
        return {"url": url, "fetched": True, "text": text}
