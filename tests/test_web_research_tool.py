from typing import Any

from fastapi.testclient import TestClient

from app.assistant.orchestrator import AssistantOrchestrator
from app.main import app


client = TestClient(app)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self.content = b""
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_web_status_disabled(monkeypatch) -> None:
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "false")

    response = client.get("/assistant/web/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_searxng_unavailable_returns_structured_error(monkeypatch) -> None:
    from app.tools.web.searxng_client import SearxngClient

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fail_get(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("httpx.get", fail_get)

    result = SearxngClient().search("test")

    assert result["error"] is True
    assert "Websuche ist nicht erreichbar" in result["message"]


def test_web_search_mocked_returns_results(monkeypatch) -> None:
    from app.tools.web.searxng_client import SearxngClient

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fake_get(*_args: Any, **_kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            {
                "results": [
                    {
                        "title": "Microsoft Learn",
                        "url": "https://learn.microsoft.com/example",
                        "content": "Offizielle Dokumentation",
                        "engine": "bing",
                    }
                ]
            }
        )

    monkeypatch.setattr("httpx.get", fake_get)

    result = SearxngClient().search("Microsoft Graph")

    assert result["query"] == "Microsoft Graph"
    assert result["provider"] == "searxng"
    assert result["results"][0]["title"] == "Microsoft Learn"


def test_web_research_returns_sources(monkeypatch) -> None:
    from app.tools.web.web_research_tool import WebResearchTool

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fake_search(_self: Any, query: str, max_results: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "provider": "searxng",
            "results": [
                {
                    "title": "Microsoft Learn",
                    "url": "https://learn.microsoft.com/example",
                    "content": "Microsoft Graph Search Dokumentation",
                    "source": "learn.microsoft.com",
                }
            ],
            "message": "1 Ergebnis gefunden.",
        }

    def fake_fetch(_self: Any, url: str) -> dict[str, Any]:
        return {"url": url, "text": "Microsoft Graph Search durchsucht Dateien.", "fetched": True}

    monkeypatch.setattr("app.tools.web.web_research_tool.SearxngClient.search", fake_search)
    monkeypatch.setattr("app.tools.web.web_research_tool.PageFetcher.fetch_text", fake_fetch)

    result = WebResearchTool().research("Microsoft Graph Search")

    assert result["sources"]
    assert result["sources"][0]["url"] == "https://learn.microsoft.com/example"
    assert "Microsoft Graph Search" in result["summary"]


def test_research_intent_routes_to_web_research(monkeypatch) -> None:
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fake_research(_self: Any, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "summary": "Microsoft Graph Search wird in der Microsoft-Dokumentation beschrieben.",
            "sources": [
                {
                    "title": "Microsoft Learn",
                    "url": "https://learn.microsoft.com/example",
                    "source": "learn.microsoft.com",
                }
            ],
            "confidence": "mittel",
            "limitations": "Nur Suchergebnisse ausgewertet.",
        }

    monkeypatch.setattr("app.tools.web.web_research_tool.WebResearchTool.research", fake_research)

    result = AssistantOrchestrator().handle_message(
        "Jarvis, recherchiere offizielle Dokumentation zu Microsoft Graph Search"
    )

    assert result["tool"] == "web_research"
    assert result["result"]["sources"]
    assert "Quellen:" in result["answer"]


def test_web_disabled_answer_does_not_claim_sources_without_search(monkeypatch) -> None:
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "false")

    result = AssistantOrchestrator().handle_message("Jarvis, suche im Internet nach Microsoft Graph Search")

    assert result["tool"] == "web_research"
    assert "Internetrecherche ist noch nicht aktiviert" in result["answer"]
    assert "Quellen:" not in result["answer"]


def test_clean_web_text_removes_microsoft_boilerplate() -> None:
    from app.tools.web.web_research_tool import clean_web_text

    cleaned = clean_web_text(
        "Zu Hauptinhalt wechseln Dieser Browser wird nicht mehr unterstützt "
        "Upgrade to Microsoft Edge Microsoft Graph Search durchsucht Inhalte."
    )

    assert "Zu Hauptinhalt wechseln" not in cleaned
    assert "Dieser Browser wird nicht mehr unterstützt" not in cleaned
    assert "Upgrade to Microsoft Edge" not in cleaned
    assert cleaned == "Microsoft Graph Search durchsucht Inhalte."


def test_microsoft_graph_query_prioritizes_learn_microsoft(monkeypatch) -> None:
    from app.tools.web.web_research_tool import WebResearchTool

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    captured: dict[str, str] = {}

    def fake_search(_self: Any, query: str, max_results: int = 5) -> dict[str, Any]:
        captured["query"] = query
        return {"query": query, "provider": "searxng", "results": [], "message": "0 Ergebnisse gefunden."}

    monkeypatch.setattr("app.tools.web.web_research_tool.SearxngClient.search", fake_search)

    WebResearchTool().research("offizielle Dokumentation zu Microsoft Graph Search")

    assert captured["query"] == "Microsoft Graph Search official documentation site:learn.microsoft.com"


def test_official_microsoft_learn_result_ranked_before_blog(monkeypatch) -> None:
    from app.tools.web.web_research_tool import WebResearchTool

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fake_search(_self: Any, query: str, max_results: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "provider": "searxng",
            "results": [
                {
                    "title": "Blog ueber Graph",
                    "url": "https://example-blog.test/graph",
                    "content": "Blog Zusammenfassung",
                    "source": "example-blog.test",
                },
                {
                    "title": "Microsoft Graph Search API",
                    "url": "https://learn.microsoft.com/graph/search",
                    "content": "Offizielle Microsoft Dokumentation",
                    "source": "learn.microsoft.com",
                },
            ],
            "message": "2 Ergebnisse gefunden.",
        }

    monkeypatch.setattr("app.tools.web.web_research_tool.SearxngClient.search", fake_search)
    monkeypatch.setattr(
        "app.tools.web.web_research_tool.PageFetcher.fetch_text",
        lambda _self, url: {"url": url, "text": "Dokumentation zu Microsoft Graph Search.", "fetched": True},
    )

    result = WebResearchTool().research("Microsoft Graph Search")

    assert result["sources"][0]["domain"] == "learn.microsoft.com"
    assert result["sources"][0]["source_quality"] == "official"
    assert result["sources"][1]["source_quality"] == "blog"


def test_research_answer_has_quality_sections_and_clean_text(monkeypatch) -> None:
    from app.tools.web.web_research_tool import WebResearchTool, format_web_research_answer

    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")

    def fake_search(_self: Any, query: str, max_results: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "provider": "searxng",
            "results": [
                {
                    "title": "Microsoft Learn Graph Search",
                    "url": "https://learn.microsoft.com/graph/search",
                    "content": "Zu Hauptinhalt wechseln Microsoft Graph Search findet Inhalte.",
                    "source": "learn.microsoft.com",
                }
            ],
            "message": "1 Ergebnis gefunden.",
        }

    monkeypatch.setattr("app.tools.web.web_research_tool.SearxngClient.search", fake_search)
    monkeypatch.setattr(
        "app.tools.web.web_research_tool.PageFetcher.fetch_text",
        lambda _self, url: {
            "url": url,
            "text": "Zu Hauptinhalt wechseln Microsoft Graph Search findet Dateien und Inhalte.",
            "fetched": True,
        },
    )

    result = WebResearchTool().research("Microsoft Graph Search")
    answer = format_web_research_answer(result)

    assert "Kurzfassung:" in answer
    assert "Beste Quellen:" in answer
    assert "Einordnung:" in answer
    assert "Zu Hauptinhalt wechseln" not in answer
    assert "https://learn.microsoft.com/graph/search" in answer
    assert result["confidence"] == "hoch"
