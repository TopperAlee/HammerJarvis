from typing import Any

from app.tools.files.file_open_tool import FileOpenTool


class AssistantSessionState:
    def __init__(self) -> None:
        self.last_file_search_results: dict[str, Any] = {"files": []}
        self.last_content_search_results: dict[str, Any] = {"files": []}
        self.last_opened_file: dict[str, Any] | None = None

    def clear(self) -> None:
        self.last_file_search_results = {"files": []}
        self.last_content_search_results = {"files": []}
        self.last_opened_file = None

    def save_file_results(self, results: dict[str, Any]) -> None:
        self.last_file_search_results = results

    def save_content_results(self, results: dict[str, Any]) -> None:
        self.last_content_search_results = results
        self.last_file_search_results = results

    def get_last_file_results(self) -> dict[str, Any]:
        return self.last_file_search_results

    def get_best_file_result(self) -> dict[str, Any] | None:
        files = self.last_file_search_results.get("files", [])
        return files[0] if files else None

    def get_result_by_index(self, index: int) -> dict[str, Any] | None:
        files = self.last_file_search_results.get("files", [])
        zero_based = index - 1
        if zero_based < 0 or zero_based >= len(files):
            return None
        return files[zero_based]


session_state = AssistantSessionState()


def open_best_match() -> dict[str, Any]:
    result = session_state.get_best_file_result()
    if not result:
        return {"opened": False, "message": "Bitte suche zuerst nach Dateien."}
    opened = FileOpenTool().open_file(str(result.get("path", "")))
    if opened.get("opened"):
        session_state.last_opened_file = opened
    return opened


def open_result_by_index(index: int) -> dict[str, Any]:
    result = session_state.get_result_by_index(index)
    if not result:
        return {"opened": False, "message": "Diesen Treffer gibt es nicht."}
    opened = FileOpenTool().open_file(str(result.get("path", "")))
    if opened.get("opened"):
        session_state.last_opened_file = opened
    return opened
