from pathlib import Path


def _dashboard_files() -> tuple[str, str, str]:
    return (
        Path("app/static/dashboard.html").read_text(encoding="utf-8"),
        Path("app/static/dashboard.js").read_text(encoding="utf-8"),
        Path("app/static/dashboard.css").read_text(encoding="utf-8"),
    )


def test_dashboard_has_safe_knowledge_upload_controls() -> None:
    html, js, _css = _dashboard_files()

    assert 'id="knowledgeDropZone"' in html
    assert 'id="knowledgeFileInput"' in html
    assert 'id="knowledgeSelectFilesButton"' in html
    assert "multiple" in html
    assert 'accept=".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.json"' in html
    assert "Erweiterte Funktion: Lokalen Pfad indexieren" in html
    assert "new FormData()" in js
    assert 'formData.append("files", file, file.name)' in js
    assert 'fetch("/assistant/knowledge/upload"' in js


def test_dashboard_knowledge_document_actions_use_document_id_and_confirmation() -> None:
    _html, js, _css = _dashboard_files()

    assert "reindexKnowledgeDocument(document, button)" in js
    assert "deleteKnowledgeDocument(document, button)" in js
    assert "if (button) button.disabled = true;" in js
    assert "encodeURIComponent(document.document_id)" in js
    assert "Soll dieses Dokument wirklich aus Jarvis’ Wissensspeicher entfernt werden?" in js
    assert "/assistant/knowledge/documents/${encodeURIComponent(document.document_id)}/reindex" in js
    assert "/assistant/knowledge/documents/${encodeURIComponent(document.document_id)}" in js


def test_knowledge_document_renderer_does_not_shadow_the_global_dom_document() -> None:
    _html, js, _css = _dashboard_files()
    start = js.index("function renderKnowledgeDocument")
    end = js.index("function createKnowledgeDocumentButton", start)
    renderer = js[start:end]

    assert "function renderKnowledgeDocument(knowledgeDocument)" in renderer
    assert "function renderKnowledgeDocument(document)" not in renderer
    assert "document.createElement(" in renderer
    assert "knowledgeDocument.original_name" in renderer
    assert "showKnowledgeDetails(knowledgeDocument)" in renderer
    assert "reindexKnowledgeDocument(knowledgeDocument, button)" in renderer
    assert "deleteKnowledgeDocument(knowledgeDocument, button)" in renderer
    assert '|| "Unbenanntes Dokument"' in renderer


def test_dashboard_knowledge_status_list_and_partial_upload_states_are_rendered() -> None:
    _html, js, _css = _dashboard_files()

    assert 'fetchJson("/assistant/knowledge/status")' in js
    assert 'fetchJson("/assistant/knowledge/documents")' in js
    assert "file_too_large" in js
    assert "invalid_pdf_header" in js
    assert "Duplikat" in js
    assert "OCR erforderlich" in js
    assert "knowledgeUploadQueue" in js
    assert "knowledgeUploadSummary" in js


def test_chat_sources_are_scoped_and_do_not_render_paths_or_chunk_ids() -> None:
    _html, js, css = _dashboard_files()

    assert "function addChatMessage(role, message, knowledgeSources = [])" in js
    assert "new Set(knowledgeSources.map" in js
    assert "response.knowledge_sources || []" in js
    assert "source.path" not in js[js.index("function addChatMessage"):js.index("function extractChatAnswer")]
    assert "chunk_ids" not in js[js.index("function addChatMessage"):js.index("function extractChatAnswer")]
    assert ".knowledge-chat-sources" in css


def test_knowledge_dashboard_preserves_voice_and_desktop_event_hooks_without_new_polling_timer() -> None:
    _html, js, _css = _dashboard_files()

    assert 'elements.voiceButton.addEventListener("click", () => startCommandRecognition({ source: "button", autoSend: true }))' in js
    assert "new WebSocket(buildDesktopEventSocketUrl())" in js
    assert "knowledgeRefreshMs" not in js
    assert "setInterval(refreshKnowledge" not in js


def test_dashboard_uses_knowledge_ingestion_cache_busting_value() -> None:
    html, js, _css = _dashboard_files()

    assert "protool-importer-20260702" in html
    assert 'const DASHBOARD_BUILD = "protool-importer-20260702";' in js


def test_knowledge_panel_has_a_reachable_grid_area_after_actions_are_split() -> None:
    html, _js, css = _dashboard_files()

    assert 'id="knowledge" class="hud-panel actions-panel"' in html
    assert 'id="actions" class="hud-panel actions-panel"' in html
    assert ".actions-panel { grid-area: actions; }" not in css
    assert "#knowledge { grid-area: knowledge; }" in css
    assert "#actions { grid-area: actions; }" in css
    assert '"knowledge chat research"' in css
    assert css.index('"actions chat research"') < css.index('"knowledge chat research"')
    assert "grid-auto-rows: minmax(min-content, max-content);" in css
    assert "#knowledge {\n  position: absolute;" not in css
    assert "#knowledge {\n  position: fixed;" not in css
