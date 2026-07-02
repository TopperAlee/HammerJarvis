from pathlib import Path


def _dashboard_files() -> tuple[str, str, str]:
    return (
        Path("app/static/dashboard.html").read_text(encoding="utf-8"),
        Path("app/static/dashboard.js").read_text(encoding="utf-8"),
        Path("app/static/dashboard.css").read_text(encoding="utf-8"),
    )


def test_dashboard_renders_protool_assistant_panel() -> None:
    html, js, css = _dashboard_files()

    assert 'href="#protool"' in html
    assert 'id="protool" class="hud-panel protool-panel"' in html
    assert "ProTool Assistant" in html
    assert 'id="protoolFilePath"' in html
    assert 'id="protoolBrowseButton"' in html
    assert 'id="protoolSelectedFileName"' in html
    assert "Dateipfad oder Datei auswählen" in html
    assert 'id="protoolPanel"' in html
    assert 'id="protoolTextColumn"' in html
    assert 'id="protoolEncoding"' in html
    assert 'id="protoolAnalyzeButton"' in html
    assert 'id="protoolImportButton"' in html
    assert "In Engineering Graph importieren" in html
    assert "protool-panel" in css
    assert '"files chat protool"' in css
    assert '"protool"' in css
    assert '"protoolFilePath"' in js
    assert "analyzeProToolCsv" in js


def test_dashboard_protool_payload_uses_existing_analyze_endpoint() -> None:
    _html, js, _css = _dashboard_files()

    assert 'fetch("/assistant/protool/analyze", {' in js
    assert "file_path: filePath" in js
    assert "panel: elements.protoolPanel.value" in js
    assert "text_column: textColumn" in js
    assert "encoding: elements.protoolEncoding.value" in js
    assert "include_preview: Boolean(elements.protoolIncludePreview?.checked)" in js


def test_dashboard_protool_selected_file_uses_upload_analyze_endpoint() -> None:
    _html, js, _css = _dashboard_files()

    assert "selectedProToolFile" in js
    assert 'fetch("/assistant/protool/upload-analyze", {' in js
    assert 'formData.append("file", selectedProToolFile, selectedProToolFile.name)' in js
    assert 'formData.append("panel", elements.protoolPanel.value)' in js
    assert 'formData.append("text_column", String(textColumn))' in js
    assert 'formData.append("encoding", elements.protoolEncoding.value)' in js
    assert 'formData.append("include_preview", String(Boolean(elements.protoolIncludePreview?.checked)))' in js


def test_dashboard_protool_manual_path_still_uses_analyze_endpoint() -> None:
    _html, js, _css = _dashboard_files()

    assert "if (selectedProToolFile)" in js
    assert "return analyzeSelectedProToolFile(textColumn);" in js
    assert "return analyzeProToolPath(filePath, textColumn);" in js


def test_dashboard_protool_import_button_uses_import_endpoint() -> None:
    _html, js, _css = _dashboard_files()

    assert "importProToolToGraph" in js
    assert 'fetch("/assistant/protool/import", {' in js
    assert "renderProToolImportResult(payload)" in js


def test_dashboard_renders_protool_batch_controls() -> None:
    html, js, _css = _dashboard_files()

    assert 'id="protoolBatchFilePaths"' in html
    assert 'id="protoolBatchAnalyzeButton"' in html
    assert 'id="protoolIncludePreview"' in html
    assert "Panel-Vorschau anzeigen" in html
    assert 'id="protoolProjectSummary"' in html
    assert 'id="protoolFileReports"' in html
    assert "analyzeProToolBatch" in js


def test_dashboard_protool_batch_payload_is_correct() -> None:
    _html, js, _css = _dashboard_files()

    assert 'fetch("/assistant/protool/analyze-batch", {' in js
    assert "file_paths: filePaths" in js
    assert "panel: elements.protoolPanel.value" in js
    assert "text_column: textColumn" in js
    assert "encoding: elements.protoolEncoding.value" in js
    assert "include_preview: Boolean(elements.protoolIncludePreview?.checked)" in js


def test_dashboard_protool_renders_issue_table_and_empty_state() -> None:
    html, js, css = _dashboard_files()

    assert "renderProToolReport" in js
    assert "renderProToolBatchReport" in js
    assert "renderProToolIssues" in js
    assert "renderProToolPreviews" in js
    assert "Keine Probleme gefunden." in html
    assert "protoolIssuesBody" in js
    assert "protoolFileReports" in js
    assert "row" in js
    assert "type" in js
    assert "line" in js
    assert "max" in js
    assert "actual" in js
    assert "text" in js
    assert ".protool-issues-table" in css


def test_dashboard_protool_external_panel_window_assets_are_present() -> None:
    _html, js, _css = _dashboard_files()

    assert "function openProToolPanelWindow(report)" in js
    assert "window.open(\"\", \"_blank\"" in js
    assert "Keine Panel-Vorschau im Report vorhanden. Bitte Checkbox 'Panel-Vorschau anzeigen' aktivieren." in js
    assert "Vorherige" in js
    assert "Nächste" in js
    assert 'event.key === "ArrowLeft"' in js
    assert 'event.key === "ArrowRight"' in js
    assert "renderPanelPreview" in js


def test_dashboard_protool_panel_window_knows_panel_dimensions() -> None:
    _html, js, _css = _dashboard_files()

    assert "OP7: { rows: 4, columns: 20 }" in js
    assert "TD17_4x20: { rows: 4, columns: 20 }" in js
    assert "TD17_8x40: { rows: 8, columns: 40 }" in js
    assert "OP17_8x40: { rows: 8, columns: 40 }" in js
    assert "OP27_8x40: { rows: 8, columns: 40 }" in js


def test_dashboard_protool_checkbox_triggers_window_after_single_analysis() -> None:
    _html, js, _css = _dashboard_files()

    assert "if (elements.protoolIncludePreview?.checked)" in js
    assert "openProToolPanelWindow(payload)" in js


def test_dashboard_protool_batch_file_report_has_panel_button_when_preview_exists() -> None:
    _html, js, _css = _dashboard_files()

    assert "Panel öffnen" in js
    assert "openProToolPanelWindow(report)" in js
    assert "previewRows.length" in js


def test_dashboard_protool_op7_renderer_contains_branding_and_controls() -> None:
    _html, js, _css = _dashboard_files()

    assert "function buildProToolOp7PanelWindow" in js
    assert 'report?.panel === "OP7"' in js
    assert "SIEMENS" in js
    assert "SIMATIC OP7" in js
    for label in ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "ESC", "ENTER"]:
        assert label in js
    for label in ["RUN", "STOP", "SF"]:
        assert label in js


def test_dashboard_protool_op7_renderer_uses_four_lcd_rows_and_zoom_controls() -> None:
    _html, js, _css = _dashboard_files()

    assert "OP7: { rows: 4, columns: 20 }" in js
    assert "op7-lcd-row" in js
    assert "createProToolZoomControls" in js
    for zoom in ["75 %", "100 %", "150 %", "200 %"]:
        assert zoom in js
    assert "Screenshot vorbereiten" in js


def test_dashboard_protool_non_op7_uses_generic_renderer() -> None:
    _html, js, _css = _dashboard_files()

    assert "buildGenericProToolPanelWindow(panelDocument, report, previewRows)" in js
    assert 'if (report?.panel === "OP7")' in js
