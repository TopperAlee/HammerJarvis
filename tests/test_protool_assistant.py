from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.engineering.importer.protool_importer import ProToolImporter
from hammer_jarvis.tools.protool.csv_reader import read_protool_csv
from hammer_jarvis.tools.protool.report import analyze_protool_csv
from hammer_jarvis.tools.protool.validator import validate_rows


client = TestClient(app)


def test_protool_importer_imports_message_text_as_text_resources(tmp_path: Path) -> None:
    csv_path = tmp_path / "MessageText.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hydraulik bereit %d\r\n2;123456789012345678901\r\n".encode("cp1252"))

    result = ProToolImporter().import_file(csv_path, panel="OP7", text_column=2, encoding="cp1252")

    assert result["text_resource_count"] == 2
    text_nodes = [node for node in result["graph"].nodes if node.type == "TextResource"]
    assert len(text_nodes) == 2
    assert text_nodes[0].metadata["text"] == "Hydraulik bereit %d"
    assert text_nodes[0].metadata["placeholders"] == ["%d"]
    assert text_nodes[0].metadata["preview"][0] == "Hydraulik bereit %d "
    assert text_nodes[1].metadata["truncated"] is True
    assert any(edge.type == "DEFINES" and edge.target_id == text_nodes[0].id for edge in result["graph"].edges)


def test_protool_importer_uses_stable_node_ids(tmp_path: Path) -> None:
    csv_path = tmp_path / "MessageText.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hydraulik bereit\r\n".encode("cp1252"))

    first = ProToolImporter().import_file(csv_path, panel="OP7", text_column=2, encoding="cp1252")
    second = ProToolImporter().import_file(csv_path, panel="OP7", text_column=2, encoding="cp1252")

    first_ids = [node.id for node in first["graph"].nodes]
    second_ids = [node.id for node in second["graph"].nodes]
    assert first_ids == second_ids


def test_upload_analyze_endpoint_is_in_openapi() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/assistant/protool/upload-analyze" in response.json()["paths"]
    assert "/assistant/protool/import" in response.json()["paths"]


def test_cp1252_csv_with_semicolon(tmp_path: Path) -> None:
    csv_path = tmp_path / "op7.csv"
    csv_path.write_bytes("ID;Text\r\n1;M\xfcller\r\n".encode("cp1252"))

    result = read_protool_csv(csv_path)

    assert result["delimiter"] == ";"
    assert result["encoding"] == "cp1252"
    assert result["rows"][1][1] == "Müller"


def test_multiline_field_is_preserved(tmp_path: Path) -> None:
    csv_path = tmp_path / "multiline.csv"
    csv_path.write_bytes('ID;Text\r\n1;"Zeile 1\r\nZeile 2"\r\n'.encode("cp1252"))

    result = read_protool_csv(csv_path)

    assert result["rows"][1][1] == "Zeile 1\r\nZeile 2"


def test_too_long_op7_text_is_reported() -> None:
    rows = [["ID", "Text"], ["1", "123456789012345678901"]]

    issues = validate_rows(rows, panel="OP7", text_column=2, encoding="cp1252")

    assert any(issue["type"] == "TEXT_TOO_LONG" for issue in issues)
    issue = next(issue for issue in issues if issue["type"] == "TEXT_TOO_LONG")
    assert issue["max"] == 20
    assert issue["actual"] == 21
    assert issue["row"] == 2


def test_protool_metadata_row_is_not_checked_for_text_length() -> None:
    rows = [["ID", "Text"], ["1", "$_Attrib(MultiLanguage) ist laenger als zwanzig Zeichen"]]

    issues = validate_rows(rows, panel="OP7", text_column=2, encoding="cp1252")

    assert not any(issue["type"] == "TEXT_TOO_LONG" for issue in issues)


def test_too_many_lines_is_reported() -> None:
    rows = [["ID", "Text"], ["1", "1\n2\n3\n4\n5"]]

    issues = validate_rows(rows, panel="OP7", text_column=2, encoding="cp1252")

    assert any(issue["type"] == "TOO_MANY_LINES" for issue in issues)
    issue = next(issue for issue in issues if issue["type"] == "TOO_MANY_LINES")
    assert issue["max"] == 4
    assert issue["actual"] == 5


def test_placeholders_are_documented_without_issue(tmp_path: Path) -> None:
    csv_path = tmp_path / "placeholders.csv"
    csv_path.write_bytes("ID;Text\r\n1;Wert <###> %d {0} %s %02d\r\n".encode("cp1252"))

    report = analyze_protool_csv(csv_path, panel="OP7", text_column=2, encoding="cp1252")

    assert not any(issue["type"] == "PLACEHOLDER" for issue in report["issues"])
    assert not any(issue["type"] == "PLACEHOLDER_MISMATCH" for issue in report["issues"])
    assert report["placeholder_count"] == 5
    assert report["placeholders"] == [
        {
            "row": 2,
            "placeholders": ["<###>", "%d", "{0}", "%s", "%02d"],
            "text": "Wert <###> %d {0} %s %02d",
        }
    ]


def test_placeholder_mismatch_is_reported_for_language_versions(tmp_path: Path) -> None:
    csv_path = tmp_path / "placeholder_mismatch.csv"
    csv_path.write_bytes(
        "ID;Text\r\n"
        "17;Wert %02d bereit {0}\r\n"
        "17;Wartosc bereit {0}\r\n".encode("cp1252")
    )

    report = analyze_protool_csv(csv_path, panel="TD17_8x40", text_column=2, encoding="cp1252")

    mismatches = [issue for issue in report["issues"] if issue["type"] == "PLACEHOLDER_MISMATCH"]
    assert len(mismatches) == 1
    assert mismatches[0]["row"] == 3
    assert mismatches[0]["expected"] == ["%02d", "{0}"]
    assert mismatches[0]["actual"] == ["{0}"]


def test_placeholder_count_is_correct(tmp_path: Path) -> None:
    csv_path = tmp_path / "placeholder_count.csv"
    csv_path.write_bytes("ID;Text\r\n1;A %d %s\r\n2;B {0} <###>\r\n".encode("cp1252"))

    report = analyze_protool_csv(csv_path, panel="TD17_8x40", text_column=2, encoding="cp1252")

    assert report["placeholder_count"] == 4
    assert [item["placeholders"] for item in report["placeholders"]] == [["%d", "%s"], ["{0}", "<###>"]]


def test_placeholder_tokens_are_detected() -> None:
    rows = [["ID", "Text"], ["1", "Wert <###> %d {0} %s"]]

    issues = validate_rows(rows, panel="OP7", text_column=2, encoding="cp1252")

    assert not any(issue["type"] == "PLACEHOLDER" for issue in issues)


def test_invalid_panel_id_raises_value_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "invalid_panel.csv"
    csv_path.write_text("ID;Text\r\n1;Hallo\r\n", encoding="cp1252")

    with pytest.raises(ValueError, match="Unsupported panel"):
        analyze_protool_csv(csv_path, panel="UNKNOWN", text_column=2)


def test_invalid_text_column_raises_value_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "invalid_column.csv"
    csv_path.write_text("ID;Text\r\n1;Hallo\r\n", encoding="cp1252")

    with pytest.raises(ValueError, match="text_column"):
        analyze_protool_csv(csv_path, panel="OP7", text_column=3)


def test_analyze_endpoint_returns_json_report(tmp_path: Path) -> None:
    csv_path = tmp_path / "endpoint.csv"
    csv_path.write_bytes("ID;Text\r\n1;123456789012345678901\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze",
        json={
            "file_path": str(csv_path),
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["file"] == str(csv_path)
    assert report["panel"] == "OP7"
    assert report["encoding"] == "cp1252"
    assert report["delimiter"] == ";"
    assert report["rows"] == 2
    assert report["checked_rows"] == 2
    assert report["issues"][0]["type"] == "TEXT_TOO_LONG"


def test_protool_import_endpoint_returns_graph_and_text_store(tmp_path: Path) -> None:
    csv_path = tmp_path / "MessageText.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hydraulik bereit %d\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/import",
        json={
            "file_path": str(csv_path),
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"] == str(csv_path)
    assert payload["panel"] == "OP7"
    assert payload["text_resource_count"] == 1
    text_nodes = [node for node in payload["graph"]["nodes"] if node["type"] == "TextResource"]
    assert text_nodes[0]["metadata"]["placeholders"] == ["%d"]

    texts_response = client.get("/assistant/protool/texts")
    assert texts_response.status_code == 200
    texts = texts_response.json()["texts"]
    assert texts[0]["id"] == text_nodes[0]["id"]

    text_response = client.get(f"/assistant/protool/text/{text_nodes[0]['id']}")
    assert text_response.status_code == 200
    assert text_response.json()["metadata"]["text"] == "Hydraulik bereit %d"


def test_analyze_report_counts_only_checked_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "checked_rows.csv"
    csv_path.write_bytes(
        "ID;Text\r\n"
        "1;$_Attrib(MultiLanguage) ist laenger als zwanzig Zeichen\r\n"
        "2;\r\n"
        "3;Normal\r\n".encode("cp1252")
    )

    report = analyze_protool_csv(csv_path, panel="OP7", text_column=2, encoding="cp1252")

    assert report["rows"] == 4
    assert report["checked_rows"] == 2
    assert not any(issue["type"] == "TEXT_TOO_LONG" for issue in report["issues"])


def test_analyze_endpoint_rejects_invalid_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "endpoint_invalid.csv"
    csv_path.write_text("ID;Text\r\n1;Hallo\r\n", encoding="cp1252")

    response = client.post(
        "/assistant/protool/analyze",
        json={
            "file_path": str(csv_path),
            "panel": "OP7",
            "text_column": 4,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 400
    assert "text_column" in response.json()["detail"]


def test_upload_analyze_endpoint_accepts_csv_file() -> None:
    response = client.post(
        "/assistant/protool/upload-analyze",
        data={
            "panel": "OP7",
            "text_column": "2",
            "encoding": "cp1252",
            "include_preview": "false",
        },
        files={"file": ("MessageText.csv", b"ID;Text\r\n1;Hallo\r\n", "text/csv")},
    )

    assert response.status_code == 200
    report = response.json()
    assert "workspace" in report["file"]
    assert "protool_uploads" in report["file"]
    assert report["panel"] == "OP7"
    assert report["rows"] == 2
    assert "previews" not in report


def test_upload_analyze_endpoint_include_preview_true() -> None:
    response = client.post(
        "/assistant/protool/upload-analyze",
        data={
            "panel": "OP7",
            "text_column": "2",
            "encoding": "cp1252",
            "include_preview": "true",
        },
        files={"file": ("MessageText.csv", b"ID;Text\r\n1;Hallo\r\n", "text/csv")},
    )

    assert response.status_code == 200
    report = response.json()
    assert "protool_uploads" in report["file"]
    assert report["preview_rows"][0]["preview"][0] == "Hallo               "


def test_analyze_batch_endpoint_accepts_two_valid_csvs(tmp_path: Path) -> None:
    first_path = tmp_path / "MessageText.csv"
    second_path = tmp_path / "InfoHelpText.csv"
    first_path.write_bytes("ID;Text\r\n1;Hallo\r\n".encode("cp1252"))
    second_path.write_bytes("ID;Text\r\n1;Welt\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze-batch",
        json={
            "file_paths": [str(first_path), str(second_path)],
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["files"]) == 2
    assert payload["summary"] == {
        "file_count": 2,
        "total_rows": 4,
        "total_checked_rows": 4,
        "total_issues": 0,
    }


def test_analyze_batch_endpoint_missing_file_returns_404_with_filename(tmp_path: Path) -> None:
    existing_path = tmp_path / "MessageText.csv"
    missing_path = tmp_path / "InfoHelpText.csv"
    existing_path.write_bytes("ID;Text\r\n1;Hallo\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze-batch",
        json={
            "file_paths": [str(existing_path), str(missing_path)],
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 404
    assert "InfoHelpText.csv" in response.json()["detail"]


def test_analyze_batch_endpoint_counts_total_issues(tmp_path: Path) -> None:
    first_path = tmp_path / "MessageText.csv"
    second_path = tmp_path / "InfoHelpText.csv"
    first_path.write_bytes("ID;Text\r\n1;123456789012345678901\r\n".encode("cp1252"))
    second_path.write_bytes('ID;Text\r\n1;"1\n2\n3\n4\n5"\r\n'.encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze-batch",
        json={
            "file_paths": [str(first_path), str(second_path)],
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["file_count"] == 2
    assert payload["summary"]["total_issues"] == 2


def test_analyze_report_without_preview_does_not_include_previews(tmp_path: Path) -> None:
    csv_path = tmp_path / "no_preview.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hydraulik bereit\r\n".encode("cp1252"))

    report = analyze_protool_csv(csv_path, panel="OP7", text_column=2, encoding="cp1252")

    assert "previews" not in report


def test_analyze_report_with_preview_includes_panel_lines(tmp_path: Path) -> None:
    csv_path = tmp_path / "preview.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hydraulik bereit\r\n".encode("cp1252"))

    report = analyze_protool_csv(
        csv_path,
        panel="OP7",
        text_column=2,
        encoding="cp1252",
        include_preview=True,
    )

    assert report["previews"] == [
        {
            "row": 2,
            "text": "Hydraulik bereit",
            "preview": [
                "Hydraulik bereit    ",
                "                    ",
                "                    ",
                "                    ",
            ],
            "truncated": False,
        }
    ]
    assert report["preview_rows"] == [
        {
            "row": 2,
            "text": "Hydraulik bereit",
            "preview": [
                "Hydraulik bereit    ",
                "                    ",
                "                    ",
                "                    ",
            ],
            "truncated": False,
            "placeholders": [],
        }
    ]


def test_preview_rows_include_placeholders(tmp_path: Path) -> None:
    csv_path = tmp_path / "preview_placeholders.csv"
    csv_path.write_bytes("ID;Text\r\n1;Wert %02d {0}\r\n".encode("cp1252"))

    report = analyze_protool_csv(
        csv_path,
        panel="OP7",
        text_column=2,
        encoding="cp1252",
        include_preview=True,
    )

    assert report["preview_rows"][0]["placeholders"] == ["%02d", "{0}"]


def test_language_header_is_not_validated_or_previewed(tmp_path: Path) -> None:
    csv_path = tmp_path / "language_header.csv"
    csv_path.write_bytes("ID;Text\r\n1;21(1) Polish\r\n2;Hydraulik bereit\r\n".encode("cp1252"))

    report = analyze_protool_csv(
        csv_path,
        panel="OP7",
        text_column=2,
        encoding="cp1252",
        include_preview=True,
    )

    assert report["checked_rows"] == 2
    assert not any(issue.get("text") == "21(1) Polish" for issue in report["issues"])
    assert [preview["text"] for preview in report["previews"]] == ["Hydraulik bereit"]


def test_analyze_report_preview_marks_long_text_as_truncated(tmp_path: Path) -> None:
    csv_path = tmp_path / "truncated.csv"
    csv_path.write_bytes("ID;Text\r\n1;123456789012345678901\r\n".encode("cp1252"))

    report = analyze_protool_csv(
        csv_path,
        panel="OP7",
        text_column=2,
        encoding="cp1252",
        include_preview=True,
    )

    assert report["previews"][0]["preview"][0] == "12345678901234567890"
    assert report["previews"][0]["truncated"] is True


def test_analyze_batch_endpoint_include_preview_false_omits_previews(tmp_path: Path) -> None:
    csv_path = tmp_path / "batch_no_preview.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hallo\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze-batch",
        json={
            "file_paths": [str(csv_path)],
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
            "include_preview": False,
        },
    )

    assert response.status_code == 200
    assert "previews" not in response.json()["files"][0]


def test_analyze_batch_endpoint_include_preview_true_returns_previews(tmp_path: Path) -> None:
    csv_path = tmp_path / "batch_preview.csv"
    csv_path.write_bytes("ID;Text\r\n1;Hallo\r\n".encode("cp1252"))

    response = client.post(
        "/assistant/protool/analyze-batch",
        json={
            "file_paths": [str(csv_path)],
            "panel": "OP7",
            "text_column": 2,
            "encoding": "cp1252",
            "include_preview": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["files"][0]["previews"][0]["preview"][0] == "Hallo               "
