import json
import os
import re
from typing import Any

from app.agent.core import normalize_message
from app.agent.permissions import ActionRisk
from app.assistant.actions.action_executor import ActionExecutor
from app.assistant.actions.action_planner import ActionPlanner
from app.assistant.actions.pending_action_store import pending_action_store
from app.assistant.formatters.ecoflow_formatter import format_ecoflow_energy_answer
from app.assistant.llm_client import LLMClient, sanitize_identity_response
from app.assistant.missions import MissionController
from app.assistant.skills.skill_registry import SkillRegistry
from app.assistant.system_prompt import SYSTEM_PROMPT
from app.assistant.tool_registry import ToolRegistry
from app.assistant.watchers import WatcherController
from app.config.personal_priority_rules import add_sender_rule
from app.logging_utils.audit import write_audit_log
from app.tools.files.file_search_tool import get_file_search_status
from app.tools.productivity.email_service import clean_email_snippet
from app.tools.web.web_research_tool import format_web_research_answer


class AssistantOrchestrator:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.llm_client = llm_client or LLMClient()

    def handle_message(self, message: str, confirm: bool = False) -> dict[str, Any]:
        normalized = normalize_message(message)
        if _is_email_send_intent(normalized) or _is_email_create_intent(normalized):
            return self._handle_rule_based(message, normalized, confirm)
        priority_feedback = _handle_priority_feedback(message)
        if priority_feedback:
            return priority_feedback
        watcher_response = _handle_watcher_command(normalized)
        if watcher_response:
            return watcher_response
        action_response = self._handle_action_command(normalized)
        if action_response:
            return action_response
        skill_response = self._handle_skill_command(message, normalized)
        if skill_response:
            return skill_response
        web_response = self._handle_web_research_command(message, normalized)
        if web_response:
            return web_response
        file_action_response = self._handle_file_result_action(normalized)
        if file_action_response:
            return file_action_response
        content_response = self._handle_file_content_command(normalized)
        if content_response:
            return content_response
        file_response = self._handle_file_command(normalized)
        if file_response:
            return file_response
        mission_controller = MissionController(registry=self.registry)
        mission_name = mission_controller.detect_mission(message)
        if mission_name:
            mission_result = mission_controller.run_mission(mission_name, message)
            planned_actions = ActionPlanner().create_actions_from_mission(mission_result)
            answer = _append_pending_actions(mission_result.get("answer", ""), planned_actions)
            return {
                "mode": "mission",
                "tool": mission_name,
                "risk": ActionRisk.GREEN,
                **mission_result,
                "answer": answer,
                "pending_actions": planned_actions,
            }
        known_route = _known_tool_route(message, normalized)
        if known_route:
            tool_name, arguments = known_route
            executed = self.registry.execute_tool(tool_name, arguments, confirm=confirm)
            tool_result = executed.get("result", executed)
            return self.answer_with_tool_result(message, tool_name, tool_result)

        if self.llm_client.is_available():
            try:
                return self._handle_llm(message, confirm)
            except Exception:
                fallback = self._handle_rule_based(message, normalized, confirm)
                return {
                    **fallback,
                    "mode": "rule_based_fallback",
                    "answer": (
                        "LLM-Anbindung ist aktuell nicht erreichbar, ich nutze "
                        "den lokalen Fallback. "
                        f"{fallback.get('answer', '')}"
                    ).strip(),
                }
        return self._handle_rule_based(message, normalized, confirm)

    def answer_with_tool_result(
        self,
        user_message: str,
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        fallback_answer = _format_tool_result(tool_name, tool_result)
        if tool_name == "ecoflow_energy_overview":
            return {
                "mode": "rule_based",
                "tool": _public_tool_name(tool_name),
                "executed_tool": tool_name,
                "answer": fallback_answer,
                "risk": ActionRisk.GREEN,
                "result": tool_result,
            }
        if self.llm_client.is_available():
            try:
                response = self.llm_client.create_response_with_tools(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                        {
                            "role": "user",
                            "content": (
                                "Antworte ausschliesslich auf Basis dieses "
                                "Tool-Ergebnisses. Behaupte nicht, dass du keine "
                                "Echtzeitdaten abrufen kannst.\n"
                                f"Tool: {tool_name}\n"
                                f"Ergebnis: {json.dumps(tool_result, ensure_ascii=False)}"
                            ),
                        },
                    ],
                    [],
                )
                answer = sanitize_identity_response(
                    user_message,
                    response.get("text") or "",
                )
                if answer and not _contains_realtime_denial(answer):
                    return {
                        "mode": "llm",
                        "tool": _public_tool_name(tool_name),
                        "executed_tool": tool_name,
                        "answer": answer,
                        "risk": ActionRisk.GREEN,
                        "result": tool_result,
                    }
            except Exception:
                pass
        return {
            "mode": "rule_based",
            "tool": _public_tool_name(tool_name),
            "executed_tool": tool_name,
            "answer": fallback_answer,
            "risk": ActionRisk.GREEN,
            "result": tool_result,
        }

    def _handle_llm(self, message: str, confirm: bool) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        tools = self.registry.get_openai_tool_schemas()
        first_response = self.llm_client.create_response_with_tools(messages, tools)
        tool_calls = first_response.get("tool_calls", [])
        if not tool_calls:
            answer = sanitize_identity_response(
                message,
                first_response.get("text") or "",
            )
            if _contains_fake_placeholder(answer):
                answer = _placeholder_guard_answer()
            return {
                "mode": "llm",
                "tool": "general_answer",
                "answer": answer,
                "risk": ActionRisk.GREEN,
            }

        max_calls = int(os.getenv("LLM_MAX_TOOL_CALLS", "5"))
        tool_outputs = []
        for call in tool_calls[:max_calls]:
            output = self.registry.execute_tool(
                str(call.get("name", "")),
                call.get("arguments", {}) or {},
                confirm=confirm,
            )
            tool_outputs.append(
                {
                    "tool_call_id": call.get("id"),
                    "name": call.get("name"),
                    "output": output,
                }
            )

        final_response = self.llm_client.final_response_with_tool_outputs(
            messages,
            tool_calls[:max_calls],
            tool_outputs,
        )
        answer = sanitize_identity_response(
            message,
            final_response.get("text") or "",
        )
        if _contains_fake_placeholder(answer):
            answer = _placeholder_guard_answer()
        return {
            "mode": "llm",
            "tool": "llm_orchestrator",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "tool_outputs": tool_outputs,
        }

    def _handle_rule_based(
        self,
        message: str,
        normalized: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if _is_ecoflow_intent(normalized):
            result = self.registry.run("ecoflow_energy_overview")
            answer = format_ecoflow_energy_answer(result)
            return self._tool_response("ecoflow_energy_overview", answer, result)

        if _is_home_assistant_problem_intent(normalized):
            result = self.registry.run("home_assistant_get_problems")
            answer = _format_home_assistant_problems(result)
            return self._tool_response("home_assistant_get_problems", answer, result)

        if _is_timetree_intent(normalized):
            result = self.registry.run("timetree_today")
            return self._tool_response(
                "timetree_today",
                _format_timetree_today_answer(result),
                result,
            )

        if _is_email_send_intent(normalized):
            result = self.registry.run("email_send_blocked")
            return {
                "mode": "rule_based",
                "tool": "email_send_blocked",
                "answer": result["message"],
                "risk": ActionRisk.RED,
                "blocked": True,
                "result": result,
            }

        if _is_email_create_intent(normalized):
            result = self.registry.run("email_create_draft")
            return {
                "mode": "rule_based",
                "tool": "email_create_draft",
                "answer": result["message"],
                "confirmation_required": True,
                "risk": ActionRisk.YELLOW,
                "proposed_action": {"tool": "email_create_draft", "message": message},
                "result": result,
            }

        if _is_email_search_intent(normalized):
            query = _build_email_search_query(message, normalized)
            tool_name = "gmail_unread_recent" if _is_unread_email_query(normalized) else "gmail_search"
            result = self.registry.run(tool_name, query=query) if tool_name == "gmail_search" else self.registry.run(tool_name)
            answer = _gmail_error_answer() if _has_gmail_error(result) else _format_email_answer(result)
            return self._tool_response(tool_name, answer, result)

        if _is_calendar_create_intent(normalized):
            result = self.registry.run("calendar_create_event")
            return {
                "mode": "rule_based",
                "tool": "calendar_create_event",
                "answer": result["message"],
                "confirmation_required": True,
                "risk": ActionRisk.YELLOW,
                "proposed_action": {"tool": "calendar_create_event", "message": message},
                "result": result,
            }

        if _is_calendar_today_intent(normalized):
            result = self.registry.run("calendar_today")
            return self._tool_response("calendar_today", result["message"], result)

        llm_result = self.llm_client.generate_response(message)
        write_audit_log("assistant_general_answer", {"mode": llm_result["mode"]})
        return {
            "mode": llm_result["mode"],
            "tool": "general_answer",
            "answer": llm_result["answer"],
            "risk": ActionRisk.GREEN,
        }

    def _tool_response(
        self,
        tool_name: str,
        answer: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        write_audit_log(
            "assistant_tool",
            {"tool": tool_name, "risk": tool.risk, "requires_confirmation": False},
        )
        return {
            "mode": "rule_based",
            "tool": tool_name,
            "answer": answer,
            "risk": tool.risk,
            "result": result,
        }

    def _handle_skill_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        skill_name, input_data = _skill_route(original, normalized)
        if not skill_name:
            return None
        if skill_name in {"document_summarize", "document_extract_key_fields"} and not input_data.get("path"):
            return {
                "mode": "rule_based",
                "tool": skill_name,
                "answer": (
                    "Ich brauche zuerst eine Datei oder einen vorherigen Suchtreffer. "
                    "Soll ich nach Kaufvertrag suchen?"
                ),
                "risk": ActionRisk.GREEN,
                "result": {"missing_context": True},
            }
        result = SkillRegistry(self.registry).execute(skill_name, input_data)
        public_tool = {
            "document_summarize": "file_summarize",
            "document_extract_key_fields": "file_extract_key_fields",
        }.get(skill_name, skill_name)
        return {
            "mode": "skill",
            "tool": public_tool,
            "executed_tool": skill_name,
            "answer": _format_skill_answer(skill_name, result),
            "risk": ActionRisk.GREEN,
            "result": result,
        }

    def _handle_action_command(self, normalized: str) -> dict[str, Any] | None:
        if _is_pending_actions_query(normalized):
            actions = pending_action_store.list_pending_actions()
            return {
                "mode": "rule_based",
                "tool": "actions_pending",
                "answer": _format_pending_actions(actions),
                "risk": ActionRisk.GREEN,
                "result": {"actions": actions, "count": len(actions)},
            }
        action = _pending_action_from_message(normalized)
        if action and _is_action_reject_intent(normalized):
            if not action:
                return _action_not_found_response()
            result = pending_action_store.reject_action(action["id"])
            return {
                "mode": "rule_based",
                "tool": "action_reject",
                "answer": f"Aktion abgelehnt: {result.get('title', '')}",
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if action and (_is_action_execute_intent(normalized) or _is_action_reference(normalized)):
            result = ActionExecutor(registry=self.registry).execute(
                action["id"],
                confirm=_is_action_confirm_intent(normalized),
            )
            return {
                "mode": "rule_based",
                "tool": "action_execute",
                "answer": _format_action_execution_answer(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        return None

    def _handle_file_command(self, normalized: str) -> dict[str, Any] | None:
        if _is_onedrive_file_intent(normalized):
            status = get_file_search_status()
            if not status.get("onedrive_configured"):
                return {
                    "mode": "rule_based",
                    "tool": "file_search_status",
                    "executed_tool": "file_search_status",
                    "answer": (
                        "OneDrive ist lokal noch nicht als Suchordner konfiguriert. "
                        "Setze FILE_SEARCH_ALLOWED_DIRS auf deinen OneDrive-Sync-Ordner."
                    ),
                    "risk": ActionRisk.GREEN,
                    "result": status,
                }

        if _is_file_open_latest_intent(normalized):
            result = self.registry.run("file_open_latest_export")
            return {
                "mode": "rule_based",
                "tool": "file_open_latest_export",
                "executed_tool": "file_open_latest_export",
                "answer": str(result.get("message", "Datei wurde geoeffnet.")),
                "risk": ActionRisk.GREEN,
                "result": result,
            }

        if _is_file_open_intent(normalized):
            query, extensions = _file_query_and_extension(normalized)
            result = self.registry.run("file_search", query=query, extensions=extensions, limit=5)
            files = result.get("files", [])
            if len(files) == 1:
                opened = self.registry.run("file_open", path=str(files[0]["path"]))
                return {
                    "mode": "rule_based",
                    "tool": "file_open",
                    "executed_tool": "file_open",
                    "answer": str(opened.get("message", "")),
                    "risk": ActionRisk.GREEN,
                    "result": opened,
                }
            return {
                "mode": "rule_based",
                "tool": "file_search",
                "executed_tool": "file_search",
                "answer": _format_file_search_answer(result, ask_to_choose=True),
                "risk": ActionRisk.GREEN,
                "result": result,
            }

        if _is_file_search_intent(normalized):
            query, extensions = _file_query_and_extension(normalized)
            result = self.registry.run("file_search", query=query, extensions=extensions)
            planned_actions = ActionPlanner().create_actions_from_file_search(result)
            return {
                "mode": "rule_based",
                "tool": "file_search",
                "executed_tool": "file_search",
                "answer": _append_pending_actions(_format_file_search_answer(result), planned_actions),
                "risk": ActionRisk.GREEN,
                "result": result,
                "pending_actions": planned_actions,
            }

        if not _is_file_create_intent(normalized):
            return None
        template = _file_template_for_message(normalized)
        if template is None:
            return {
                "mode": "rule_based",
                "tool": "file_create_clarification",
                "answer": (
                    "Welche Datei soll ich erstellen? Moeglich sind zum Beispiel "
                    "Excel fuer Ausgaben, Wartungsplan oder EcoFlow Tageswerte."
                ),
                "risk": ActionRisk.GREEN,
            }
        executed = self.registry.execute_tool("file_create_excel", template, confirm=False)
        result = executed.get("result", executed)
        answer = f"Ich habe die Excel-Datei erstellt:\n{result.get('path', '')}".strip()
        return {
            "mode": "rule_based",
            "tool": "file_create_excel",
            "executed_tool": "file_create_excel",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "result": result,
            **{key: result[key] for key in ("created", "file_type", "filename", "path", "message") if key in result},
        }

    def _handle_web_research_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        if not _is_web_research_intent(normalized):
            return None
        query = _web_research_query(original, normalized)
        result = self.registry.run("web_research", query=query)
        planned_actions = ActionPlanner().create_actions_from_web_research(result)
        answer = _append_pending_actions(format_web_research_answer(result), planned_actions)
        return {
            "mode": "rule_based",
            "tool": "web_research",
            "executed_tool": "web_research",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "result": result,
            "pending_actions": planned_actions,
        }

    def _handle_file_content_command(self, normalized: str) -> dict[str, Any] | None:
        if not _is_file_content_search_intent(normalized):
            return None
        query, extensions = _content_query_and_extensions(normalized)
        result = self.registry.run("file_content_search", query=query, extensions=extensions)
        planned_actions = ActionPlanner().create_actions_from_file_search(result)
        return {
            "mode": "rule_based",
            "tool": "file_content_search",
            "executed_tool": "file_content_search",
            "answer": _append_pending_actions(_format_file_content_answer(result), planned_actions),
            "risk": ActionRisk.GREEN,
            "result": result,
            "pending_actions": planned_actions,
        }

    def _handle_file_result_action(self, normalized: str) -> dict[str, Any] | None:
        if _is_open_best_match_intent(normalized):
            index = _result_index(normalized)
            if index is None:
                result = self.registry.run("file_open_best_match")
                tool_name = "file_open_best_match"
            else:
                result = self.registry.run("file_open_result_by_index", index=index)
                tool_name = "file_open_result_by_index"
            return {
                "mode": "rule_based",
                "tool": tool_name,
                "executed_tool": tool_name,
                "answer": str(result.get("message", "Datei wurde geoeffnet.")),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if _is_summarize_file_result_intent(normalized):
            from app.assistant.session_state import session_state

            best = session_state.get_best_file_result()
            if not best:
                return {
                    "mode": "rule_based",
                    "tool": "file_summarize",
                    "answer": "Bitte suche zuerst nach Dateien.",
                    "risk": ActionRisk.GREEN,
                    "result": {"error": True},
                }
            focus = "Kaufvertrag" if "kaufvertrag" in normalized else None
            result = self.registry.run("file_summarize", path=str(best.get("path", "")), focus=focus)
            return {
                "mode": "rule_based",
                "tool": "file_summarize",
                "executed_tool": "file_summarize",
                "answer": str(result.get("summary", "Keine Zusammenfassung verfuegbar.")),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if _is_extract_key_fields_intent(normalized):
            from app.assistant.session_state import session_state

            best = session_state.get_best_file_result()
            if not best:
                return {
                    "mode": "rule_based",
                    "tool": "file_extract_key_fields",
                    "answer": "Bitte suche zuerst nach Dateien.",
                    "risk": ActionRisk.GREEN,
                    "result": {"error": True},
                }
            document_type = "kaufvertrag" if "kaufvertrag" in normalized else None
            result = self.registry.run("file_extract_key_fields", path=str(best.get("path", "")), document_type=document_type)
            return {
                "mode": "rule_based",
                "tool": "file_extract_key_fields",
                "executed_tool": "file_extract_key_fields",
                "answer": _format_key_fields_answer(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        return None


def _is_ecoflow_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "ecoflow",
            "batterie",
            "akku",
            "pv",
            "solar",
            "solarstrom",
            "strom",
            "energie",
            "smart meter",
            "smartmeter",
            "netzleistung",
            "verbrauch",
        )
    )


def _is_file_create_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "excel",
            "xlsx",
            "tabelle",
            "spreadsheet",
            "csv",
            "datei erstellen",
            "vorlage erstellen",
            "erstelle eine excel",
            "erstelle mir eine excel",
            "mach mir eine tabelle",
            "erstelle eine csv",
            "erstelle eine datei",
            "erstelle eine vorlage",
            "exportiere als excel",
            "exportiere",
        )
    )


def _is_file_search_intent(message: str) -> bool:
    if any(term in message for term in ("erstelle", "mach mir", "exportiere", "vorlage erstellen", "datei erstellen")):
        return False
    return any(
        term in message
        for term in (
            "pdf",
            "pdfs",
            "datei",
            "dateien",
            "dokument",
            "dokumente",
            "excel",
            "xlsx",
            "word",
            "docx",
            "onedrive",
            "one drive",
            "datei suchen",
            "finde datei",
            "suche datei",
            "wo ist",
            "finde excel",
            "finde die excel",
            "finde die excel mit",
            "finde pdf",
            "suche nach",
            "suche in onedrive",
            "suche in one drive",
            "finde in onedrive",
            "finde alle pdf",
            "suche alle pdf",
            "suche nach datei",
            "finde die datei mit",
            "hauskauf",
            "mietvertrag",
        )
    )


def _is_file_content_search_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "suche im inhalt",
            "durchsuche pdfs nach",
            "finde dateien in denen",
            "suche kaufvertrag in pdfs",
            "welche datei enthaelt",
            "welche datei enthÃ¤lt",
            "welche pdf enthaelt",
            "welche pdf enthÃ¤lt",
            "suche in dokumenten nach",
            "suche in pdfs nach",
        )
    )


def _is_open_best_match_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "oeffne den besten treffer",
            "Ã¶ffne den besten treffer",
            "oeffne die erste datei",
            "Ã¶ffne die erste datei",
            "oeffne treffer",
            "Ã¶ffne treffer",
        )
    )


def _is_summarize_file_result_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "fasse den besten treffer zusammen",
            "fasse den kaufvertrag zusammen",
            "was steht in der datei",
            "analysiere diese pdf",
            "erstelle eine zusammenfassung der datei",
        )
    )


def _is_extract_key_fields_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "extrahiere die wichtigsten daten",
            "eckdaten extrahieren",
            "wichtigsten daten aus dem kaufvertrag",
        )
    )


def _result_index(message: str) -> int | None:
    if "erste datei" in message:
        return 1
    match = re.search(r"treffer\s+(\d+)", message)
    return int(match.group(1)) if match else None


def _is_onedrive_file_intent(message: str) -> bool:
    return "onedrive" in message or "one drive" in message


def _is_file_open_latest_intent(message: str) -> bool:
    folded = _fold_german_text(message)
    if "letzte" in folded and "datei" in folded and any(
        verb in folded for verb in ("offne", "oeffne", "open")
    ):
        return True
    return any(
        term in message
        for term in (
            "oeffne letzte datei",
            "oeffne die letzte datei",
            "oeffne die letzte erstellte datei",
            "oeffne letzte erstellte datei",
            "oeffne die letzte excel",
            "Ã¶ffne letzte datei",
            "Ã¶ffne die letzte datei",
            "Ã¶ffne die letzte erstellte datei",
            "Ã¶ffne letzte erstellte datei",
            "Ã¶ffne die letzte excel",
        )
    )


def _fold_german_text(message: str) -> str:
    return (
        message.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .replace("Ã¤", "ae")
        .replace("Ã¶", "oe")
        .replace("Ã¼", "ue")
    )


def _is_file_open_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "oeffne die datei",
            "oeffne datei",
            "oeffne ausgaben",
            "oeffne die erstellte datei",
            "Ã¶ffne die datei",
            "Ã¶ffne datei",
            "Ã¶ffne ausgaben",
            "Ã¶ffne die erstellte datei",
        )
    )


def _file_query_and_extension(message: str) -> tuple[str, list[str] | None]:
    extension: str | None = None
    if "pdf" in message:
        extension = ".pdf"
    elif "excel" in message or "xlsx" in message:
        extension = ".xlsx"
    elif "word" in message or "docx" in message:
        extension = ".docx"
    elif "csv" in message:
        extension = ".csv"

    query = message
    for token in (
        "suche in onedrive nach",
        "suche in one drive nach",
        "suche in onedrive",
        "suche in one drive",
        "finde in onedrive nach",
        "finde in onedrive",
        "suche alle pdfs zum",
        "suche alle pdfs",
        "suche alle pdf zum",
        "suche alle pdf",
        "finde alle pdfs zum",
        "finde alle pdfs",
        "finde alle pdf zum",
        "finde alle pdf",
        "finde die datei mit",
        "finde datei",
        "datei suchen",
        "suche datei",
        "suche nach datei",
        "suche nach",
        "wo ist",
        "finde excel mit",
        "finde die excel mit",
        "finde excel",
        "finde pdf",
        "oeffne die datei",
        "oeffne datei",
        "oeffne",
        "Ã¶ffne die datei",
        "Ã¶ffne datei",
        "Ã¶ffne",
        "meinen",
        "meine",
        "die",
        "mit",
        "onedrive",
        "one drive",
        "zum",
        "zur",
    ):
        query = query.replace(token, " ")
    query = (
        query.replace(".xlsx", " ")
        .replace(".xls", " ")
        .replace(".pdf", " ")
        .replace(".docx", " ")
        .replace("excel", " ")
        .replace("pdfs", " ")
        .replace("pdf", " ")
        .replace("word", " ")
        .replace("docx", " ")
        .replace("csv", " ")
    )
    query = re.sub(r"[?.!,;:]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    extensions = _extensions_for_message(message, extension)
    return ((query or message.strip()).title(), extensions)


def _extensions_for_message(message: str, extension: str | None) -> list[str] | None:
    if "excel" in message or "xlsx" in message:
        return [".xlsx", ".xls"]
    return [extension] if extension else None


def _format_file_search_answer(result: dict[str, Any], ask_to_choose: bool = False) -> str:
    if not result.get("files"):
        label = _file_type_label(result.get("extensions", []))
        return (
            f"Ich habe in den erlaubten Ordnern gesucht, aber keine passende {label}gefunden. "
            "Aktuell suche ich nur Dateiname und Pfad, nicht den Inhalt von PDFs."
        )
    label = _file_type_label(result.get("extensions", []), plural=True)
    lines = [f"Ich habe {result.get('count', 0)} passende {label}gefunden:"]
    for index, file in enumerate(result.get("files", [])[:10], start=1):
        lines.append(f"{index}. {file.get('name')}")
        lines.append(f"   {file.get('path')}")
        if file.get("modified_at"):
            lines.append(f"   {file.get('modified_at')}")
    if ask_to_choose and result.get("files"):
        lines.append("Welche Datei soll ich oeffnen?")
    return "\n".join(lines)


def _content_query_and_extensions(message: str) -> tuple[str, list[str] | None]:
    extensions: list[str] | None = None
    if "pdf" in message:
        extensions = [".pdf"]
    elif "dokument" in message or "docx" in message or "word" in message:
        extensions = [".docx", ".pdf", ".txt", ".md", ".csv", ".xlsx", ".xlsm", ".json"]
    query = message
    for token in (
        "suche im inhalt nach",
        "suche im inhalt",
        "durchsuche pdfs nach",
        "finde dateien in denen",
        "suche kaufvertrag in pdfs",
        "welche datei enthaelt",
        "welche datei enthÃ¤lt",
        "welche pdf enthaelt",
        "welche pdf enthÃ¤lt",
        "suche in dokumenten nach",
        "suche in pdfs nach",
        "steht",
        "pdfs",
        "pdf",
    ):
        query = query.replace(token, " ")
    query = re.sub(r"[?.!,;:]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if "kaufvertrag in" in message:
        query = "kaufvertrag"
    return ((query or message).title(), extensions)


def _format_file_content_answer(result: dict[str, Any]) -> str:
    if not result.get("files"):
        return "Ich habe in den erlaubten Ordnern gesucht, aber keine Inhaltstreffer gefunden."
    lines = [f"Ich habe {result.get('count', 0)} Dateien mit Inhaltstreffern gefunden:"]
    for index, file in enumerate(result.get("files", [])[:10], start=1):
        lines.append(f"{index}. {file.get('name')}")
        lines.append(f"   {file.get('path')}")
        for snippet in file.get("snippets", [])[:2]:
            lines.append(f"   Treffer: {snippet}")
    return "\n".join(lines)


def _format_key_fields_answer(result: dict[str, Any]) -> str:
    snippets = result.get("key_snippets", {})
    if not snippets:
        return "Ich habe keine Eckdaten gefunden."
    lines = ["Gefundene Eckdaten:"]
    for key, values in snippets.items():
        lines.append(f"- {key}: {values[0]}")
    return "\n".join(lines)


def _file_type_label(extensions: list[str], plural: bool = False) -> str:
    if ".pdf" in extensions:
        return "PDF-Dateien " if plural else "PDF-Datei "
    if ".xlsx" in extensions or ".xls" in extensions:
        return "Excel-Dateien " if plural else "Excel-Datei "
    if ".docx" in extensions:
        return "Word-Dateien " if plural else "Word-Datei "
    return "Dateien " if plural else "Datei "


def _is_web_research_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "recherchiere",
            "suche im internet",
            "suche online",
            "finde offizielle dokumentation",
            "pruefe im internet",
            "prÃ¼fe im internet",
            "aktuelle informationen",
            "websuche",
        )
    )


def _web_research_query(original: str, normalized: str) -> str:
    query = normalize_message(original, lowercase=False)
    for token in (
        "Jarvis",
        "jarvis",
        "recherchiere",
        "suche im Internet nach",
        "suche im internet nach",
        "suche online nach",
        "finde offizielle Dokumentation zu",
        "finde offizielle dokumentation zu",
        "prÃ¼fe im Internet",
        "pruefe im internet",
        "websuche",
    ):
        query = query.replace(token, " ")
    query = re.sub(r"[?.!,;:]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return query or normalized


def _file_template_for_message(message: str) -> dict[str, Any] | None:
    if "ausgaben" in message:
        return {
            "title": "Ausgaben",
            "filename": "ausgaben.xlsx",
            "sheets": [
                {
                    "name": "Ausgaben",
                    "headers": ["Datum", "Kategorie", "Beschreibung", "Betrag", "Zahlungsart", "Notiz"],
                    "rows": [],
                }
            ],
        }
    if "wartungsplan" in message:
        return {
            "title": "Wartungsplan",
            "filename": "wartungsplan.xlsx",
            "sheets": [
                {
                    "name": "Wartungsplan",
                    "headers": [
                        "Maschine",
                        "Bereich",
                        "Aufgabe",
                        "Intervall",
                        "Verantwortlich",
                        "Letzte Wartung",
                        "Naechste Wartung",
                        "Status",
                    ],
                    "rows": [],
                }
            ],
        }
    if "ecoflow" in message and ("tageswerte" in message or "excel" in message):
        return {
            "title": "EcoFlow Tageswerte",
            "filename": "ecoflow_tageswerte.xlsx",
            "sheets": [
                {
                    "name": "EcoFlow Tageswerte",
                    "headers": [
                        "Datum",
                        "Batterie %",
                        "PV-Leistung W",
                        "Netzleistung W",
                        "Smart Meter W",
                        "Verbrauch Wh",
                        "Netzbezug Wh",
                        "Hinweis",
                    ],
                    "rows": [],
                }
            ],
        }
    return None


def _skill_route(original: str, normalized: str) -> tuple[str | None, dict[str, Any]]:
    if _is_web_research_excel_skill_intent(normalized):
        return "web_research_excel", {"query": _web_research_query(original, normalized)}
    if _is_web_research_report_skill_intent(normalized):
        return "web_research_report", {"query": _web_research_query(original, normalized)}
    if _is_document_index_excel_skill_intent(normalized):
        query, extensions = _file_query_and_extension(normalized)
        return "document_index_excel", {"query": query, "extensions": extensions or [".pdf"]}
    if _is_file_search_report_skill_intent(normalized):
        query, extensions = _content_query_and_extensions(normalized)
        return "file_search_report", {"query": query, "extensions": extensions, "content_search": _is_file_content_search_intent(normalized)}
    if _is_document_summarize_skill_intent(normalized):
        return "document_summarize", {"path": _best_result_path(), "focus": "Kaufvertrag" if "kaufvertrag" in normalized else None}
    if _is_document_extract_skill_intent(normalized):
        return "document_extract_key_fields", {"path": _best_result_path(), "document_type": "kaufvertrag" if "kaufvertrag" in normalized else "unknown"}
    return None, {}


def _best_result_path() -> str:
    from app.assistant.session_state import session_state

    best = session_state.get_best_file_result()
    return str(best.get("path", "")) if best else ""


def _is_web_research_excel_skill_intent(message: str) -> bool:
    return _is_web_research_intent(message) and any(term in message for term in ("excel", "xlsx", "quellenliste"))


def _is_web_research_report_skill_intent(message: str) -> bool:
    return _is_web_research_intent(message) and any(term in message for term in ("bericht", "markdown", "quellenuebersicht", "quellenÃ¼bersicht"))


def _is_document_index_excel_skill_intent(message: str) -> bool:
    if not any(term in message for term in ("excel", "xlsx", "uebersicht", "Ã¼bersicht", "liste", "index")):
        return False
    return any(term in message for term in ("dokument", "dokumente", "pdf", "pdfs", "suchergebnisse", "ergebnisse", "hauskauf"))


def _is_file_search_report_skill_intent(message: str) -> bool:
    return any(term in message for term in ("suchbericht", "bericht ueber", "bericht Ã¼ber", "dokumentiere die gefundenen"))


def _is_document_summarize_skill_intent(message: str) -> bool:
    return any(term in message for term in ("fasse diese datei zusammen", "fasse den besten treffer zusammen", "fasse den kaufvertrag zusammen", "was steht in treffer"))


def _is_document_extract_skill_intent(message: str) -> bool:
    return any(term in message for term in ("extrahiere die wichtigsten daten", "welche eckdaten", "kerndaten", "eckdaten stehen"))


def _format_skill_answer(skill_name: str, result: dict[str, Any]) -> str:
    if result.get("blocked"):
        return str(result.get("message", "Aktion wurde aus Sicherheitsgruenden blockiert."))
    if skill_name == "document_summarize":
        return str(result.get("summary", "Keine Zusammenfassung verfuegbar."))
    if skill_name == "document_extract_key_fields":
        lines = ["Gefundene Eckdaten:"]
        for key, value in result.get("fields", {}).items():
            lines.append(f"- {key}: {value.get('value', 'nicht gefunden')}")
        return "\n".join(lines)
    if skill_name in {"file_search_report", "web_research_report"}:
        return f"{result.get('message', 'Bericht wurde erstellt.')}\n{result.get('path', '')}".strip()
    if skill_name in {"document_index_excel", "web_research_excel"}:
        return f"{result.get('message', 'Excel-Datei wurde erstellt.')}\n{result.get('path', '')}".strip()
    return str(result.get("message", "Skill wurde ausgefuehrt."))


def _is_pending_actions_query(message: str) -> bool:
    return any(term in message for term in ("was schlaegst du vor", "was schlÃ¤gst du vor", "welche aktionen stehen aus", "zeige aktionen"))


def _is_action_execute_intent(message: str) -> bool:
    if _leading_action_index(message) is not None:
        return True
    if "aktion" in message and any(
        term in message
        for term in ("fuehre", "führe", "fÃ¼hre", "aus", "bestaetige", "bestätige", "bestÃ¤tige", "confirm", "best")
    ):
        return True
    if any(term in _fold_german_text(message) for term in ("ausfuehren", "fuehre", "bestatige", "bestaetige")):
        return True
    return False


def _is_action_confirm_intent(message: str) -> bool:
    folded = _fold_german_text(message)
    return any(
        term in message
        for term in ("bestaetige", "bestätige", "bestÃ¤tige", "confirm", "mit bestaetigung", "mit bestätigung", "mit bestÃ¤tigung", "best")
    ) or any(term in folded for term in ("bestaetige", "bestatige", "confirm"))


def _is_action_reject_intent(message: str) -> bool:
    return any(term in message for term in ("aktion", "vorschlag")) and any(term in message for term in ("ablehnen", "verwerfen", "reject"))


def _action_index(message: str) -> int | None:
    match = re.search(r"aktion\s+(\d+)", message)
    if not match:
        match = re.search(r"vorschlag\s+(\d+)", message)
    if not match:
        return _leading_action_index(message)
    return int(match.group(1))


def _leading_action_index(message: str) -> int | None:
    match = re.match(r"^\s*(\d+)\.?\b", message)
    return int(match.group(1)) if match else None


def _pending_action_from_message(message: str) -> dict[str, Any] | None:
    index = _action_index(message)
    if index is not None:
        return _pending_action_by_index(index)
    normalized_message = _normalize_action_reference(message)
    if not normalized_message:
        return None
    for action in pending_action_store.list_pending_actions():
        title = _normalize_action_reference(str(action.get("title") or ""))
        if title and (title in normalized_message or normalized_message in title):
            return action
    return None


def _is_action_reference(message: str) -> bool:
    return _pending_action_from_message(message) is not None


def _normalize_action_reference(value: str) -> str:
    folded = _fold_german_text(value)
    folded = re.sub(r"^\s*\d+\.?\s*", "", folded)
    folded = re.sub(r"\[(green|gruen|grun|yellow|gelb|red|rot)\]", " ", folded)
    folded = re.sub(r"\b(aktion|fuehre|fuehr|ausfuehren|ausfuehre|aus|bestatige|bestaetige|confirm)\b", " ", folded)
    folded = re.sub(r"[^a-z0-9 ]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _pending_action_by_index(index: int) -> dict[str, Any] | None:
    actions = pending_action_store.list_pending_actions()
    if index < 1 or index > len(actions):
        return None
    return actions[index - 1]


def _action_not_found_response() -> dict[str, Any]:
    return {
        "mode": "rule_based",
        "tool": "action_execute",
        "answer": "Diese Aktion ist nicht mehr ausstehend oder wurde nicht gefunden.",
        "risk": ActionRisk.GREEN,
        "result": {"error": True},
    }


def _append_pending_actions(answer: str, actions: list[dict[str, Any]]) -> str:
    if not actions:
        return answer
    return "\n\n".join([answer, _format_pending_actions(actions), "Sag: 'Führe Aktion 1 aus.'"])


def _format_pending_actions(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "Es stehen aktuell keine Aktionen aus."
    lines = ["Mögliche nächste Aktionen:"]
    for index, action in enumerate(actions[:3], start=1):
        lines.append(f"{index}. [{_risk_label(str(action.get('risk', 'GREEN')))}] {action.get('title')}")
    return "\n".join(lines)


def _format_action_execution_answer(result: dict[str, Any]) -> str:
    if result.get("confirmation_required"):
        return "Diese Aktion benötigt eine Bestätigung. Sag: 'Bestätige Aktion 1', wenn ich fortfahren soll."
    if result.get("status") == "executed":
        title = result.get("action", {}).get("title", "Aktion")
        tool_result = _executed_tool_result(result)
        if isinstance(tool_result, dict) and tool_result.get("recommendations"):
            lines = [
                f"Ausgeführt: {title}",
                "",
                str(tool_result.get("headline") or ""),
                "",
                "Empfohlene sichere Maßnahmen:",
            ]
            for index, recommendation in enumerate(tool_result.get("recommendations", []), start=1):
                lines.append(f"{index}. {recommendation}")
            lines.extend(["", "Ich habe nichts automatisch geschaltet."])
            if result.get("action", {}).get("risk") == "YELLOW":
                lines.extend(["", "Diese Aktion wurde erst nach deiner Bestätigung ausgeführt."])
            return "\n".join(line for line in lines if line is not None).strip()
        if isinstance(tool_result, dict) and tool_result.get("created") and tool_result.get("path"):
            message = str(tool_result.get("message") or "Datei wurde erstellt.").rstrip(".")
            if tool_result.get("status"):
                lines = [
                    f"{message}:",
                    str(tool_result.get("path")),
                    "",
                    f"Status: {tool_result.get('status')}",
                ]
                if tool_result.get("reason"):
                    lines.append(f"Grund: {tool_result.get('reason')}.")
                if tool_result.get("next_action"):
                    lines.append(f"Nächster Schritt: {tool_result.get('next_action')}")
                lines.append("Ich habe nichts automatisch geschaltet.")
                return "\n".join(lines)
            summary = str(tool_result.get("summary") or "").strip()
            if summary:
                return f"{message}:\n{tool_result.get('path')}\n\n{summary}"
            return f"{message}:\n{tool_result.get('path')}"
        return f"Ausgeführt: {title}"
    if result.get("status") == "blocked":
        return "Diese Aktion wurde blockiert."
    if result.get("status") == "expired":
        return "Diese Aktion ist abgelaufen."
    return str(result.get("message", "Aktion wurde verarbeitet."))


def _executed_tool_result(result: dict[str, Any]) -> dict[str, Any] | None:
    executed = result.get("result")
    if not isinstance(executed, dict):
        return None
    tool_result = executed.get("result")
    return tool_result if isinstance(tool_result, dict) else executed
def _risk_label(risk: str) -> str:
    return {
        "GREEN": "GRÜN",
        "YELLOW": "GELB",
        "RED": "ROT",
    }.get(risk.upper(), risk.upper())


def _known_tool_route(
    original_message: str,
    normalized_message: str,
) -> tuple[str, dict[str, Any]] | None:
    if _is_ecoflow_intent(normalized_message):
        return "ecoflow_energy_overview", {}
    if _is_email_search_intent(normalized_message):
        if _is_unread_email_query(normalized_message):
            return "gmail_unread_recent", {}
        return "gmail_search", {"query": _build_email_search_query(original_message, normalized_message)}
    if _is_timetree_intent(normalized_message):
        return "timetree_today", {}
    if _is_home_assistant_problem_intent(normalized_message):
        return "home_assistant_get_problems", {}
    return None


def _is_unread_email_query(message: str) -> bool:
    return "ungelesen" in message or "neue" in message or "neue mails" in message


def _is_home_assistant_problem_intent(message: str) -> bool:
    terms = (
        "home assistant diagnose",
        "welche geraete haben probleme",
        "welche gerate haben probleme",
        "gerÃ¤te probleme",
        "geraete probleme",
        "gerate probleme",
        "smart home status",
        "smart-home status",
        "probleme",
        "offline",
    )
    return any(term in message for term in terms)


def _is_email_search_intent(message: str) -> bool:
    terms = ("email", "mail", "mails", "e-mail", "e-mails", "posteingang", "nachricht", "nachrichten", "gmail")
    return any(term in message for term in terms)


def _build_email_search_query(original_message: str, normalized_message: str) -> str:
    if "ungelesene" in normalized_message or "neue e-mail" in normalized_message:
        return "is:unread newer_than:30d"
    sender_match = re.search(r"(?:e-?mails?|mails?)\s+von\s+(.+)$", original_message, re.I)
    if sender_match:
        sender = sender_match.group(1).strip(" ?!.:,;")
        if sender:
            return f"from:{sender} newer_than:90d"
    gmail_match = re.search(r"suche\s+gmail\s+nach\s+(.+)$", original_message, re.I)
    if gmail_match:
        query = gmail_match.group(1).strip()
        if query:
            return query
    return original_message


def _has_gmail_error(result: dict[str, Any]) -> bool:
    return any(
        item.get("provider") == "gmail" and item.get("error") is True
        for item in result.get("providers", [])
        if isinstance(item, dict)
    )


def _gmail_error_answer() -> str:
    return (
        "Gmail ist noch nicht korrekt verbunden. Der OAuth-Client oder das "
        "Client Secret ist ungueltig. Bitte lade die gmail_credentials.json "
        "erneut aus Google Cloud herunter. Outlook Mail ist weiterhin "
        "vorbereitet, aber noch nicht verbunden."
    )


def _format_email_answer(result: dict[str, Any]) -> str:
    lines = [str(result.get("message", "")).strip()]
    for index, email in enumerate(_collect_emails(result)[:5], start=1):
        sender = str(email.get("sender") or "Unbekannter Absender").strip()
        subject = clean_email_snippet(str(email.get("subject") or "(kein Betreff)"))
        date = str(email.get("date") or "").strip()
        item = f"{index}. {sender}: {subject}"
        if date:
            item += f" ({date})"
        lines.append(item)
    return "\n".join(line for line in lines if line)


def _format_gmail_unread_answer(result: dict[str, Any]) -> str:
    if _has_gmail_error(result):
        return _gmail_error_answer()
    count = result.get("unread_count")
    if count is None:
        count = result.get("total_email_count", 0)
    if result.get("total_email_count") == count:
        lines = [f"Ich habe {count} Gmail-Nachrichten gefunden."]
    else:
        lines = [f"Ich habe {count} ungelesene Gmail-Nachrichten gefunden."]
    for index, email in enumerate(_collect_emails(result)[:5], start=1):
        sender = str(email.get("sender") or "Unbekannter Absender").strip()
        subject = clean_email_snippet(str(email.get("subject") or "(kein Betreff)"))
        lines.append(f"{index}. {sender}: {subject}")
    return "\n".join(lines)


def _collect_emails(result: dict[str, Any]) -> list[dict[str, Any]]:
    emails: list[dict[str, Any]] = []
    for provider in result.get("providers", []):
        if isinstance(provider, dict) and provider.get("connected") is True:
            emails.extend(email for email in provider.get("emails", []) if isinstance(email, dict))
    return emails


def _is_email_create_intent(message: str) -> bool:
    return _is_email_search_intent(message) and any(term in message for term in ("schreibe", "verfasse", "erstelle", "entwurf"))


def _is_email_send_intent(message: str) -> bool:
    return _is_email_search_intent(message) and any(term in message for term in ("sende", "senden", "abschicken"))


def _is_calendar_today_intent(message: str) -> bool:
    calendar_terms = ("termin", "termine", "kalender", "meeting", "meetings", "heute im kalender", "was steht heute an")
    today_terms = ("heute", "morgen", "welche", "was steht", "habe ich")
    return any(term in message for term in calendar_terms) and any(term in message for term in today_terms)


def _is_calendar_create_intent(message: str) -> bool:
    return any(term in message for term in ("termin", "kalender", "meeting")) and any(term in message for term in ("erstelle", "anlegen", "eintragen", "plane"))


def _is_timetree_intent(message: str) -> bool:
    return "timetree" in message


def _format_timetree_today_answer(result: dict[str, Any]) -> str:
    if result.get("enabled") is False:
        return "TimeTree ist vorbereitet, aber der ICS-Import ist noch deaktiviert."
    if result.get("error"):
        return "Die lokale TimeTree ICS-Datei konnte nicht gelesen werden."
    if result.get("connected") is False:
        return str(result.get("message", "TimeTree ICS-Datei wurde nicht gefunden."))
    events = result.get("events", [])
    if not events:
        return "Heute stehen keine TimeTree-Termine in der lokalen ICS-Datei."
    lines = [f"Heute stehen {len(events)} TimeTree-Termine an:"]
    for index, event in enumerate(events, start=1):
        prefix = "GanztÃ¤gig" if event.get("all_day") else _format_event_time(event)
        lines.append(f"{index}. {prefix} {event.get('title', '')}".strip())
    return "\n".join(lines)


def _format_home_assistant_problems(result: dict[str, Any]) -> str:
    lines = [
        (
            f"Kritisch: {result.get('critical_count', 0)}, "
            f"Warnungen: {result.get('warning_count', 0)}, "
            f"Infos: {result.get('informational_count', 0)}"
        )
    ]
    for entity in (result.get("critical", []) + result.get("warning", []))[:5]:
        entity_id = entity.get("entity_id", "unknown")
        state = entity.get("state", "")
        lines.append(f"- {entity_id}: {state}".strip())
    return "\n".join(lines)


def _format_tool_result(tool_name: str, result: dict[str, Any]) -> str:
    if tool_name == "ecoflow_energy_overview":
        return format_ecoflow_energy_answer(result)
    if tool_name == "gmail_unread_recent":
        return _format_gmail_unread_answer(result)
    if tool_name == "gmail_search":
        return _gmail_error_answer() if _has_gmail_error(result) else _format_email_answer(result)
    if tool_name == "timetree_today":
        return _format_timetree_today_answer(result)
    if tool_name == "home_assistant_get_problems":
        return _format_home_assistant_problems(result)
    return str(result.get("message", "Werkzeug wurde ausgefuehrt."))


def _public_tool_name(tool_name: str) -> str:
    if tool_name in {"gmail_unread_recent", "gmail_search"}:
        return "email_search_all"
    return tool_name


def _contains_realtime_denial(answer: str) -> bool:
    normalized = answer.lower()
    return any(
        phrase in normalized
        for phrase in (
            "keine echtzeitdaten",
            "keine live-daten",
            "nicht abrufen",
            "kann aktuell keine",
        )
    )


def _contains_fake_placeholder(answer: str) -> bool:
    return any(
        placeholder in answer
        for placeholder in (
            "[Wert aus Tool]",
            "[falls verknüpft]",
            "[falls verknuepft]",
            "[Aktuelle Gerätestatus]",
            "[Aktuelle Geraetestatus]",
        )
    )


def _placeholder_guard_answer() -> str:
    return (
        "Ich erstelle keine Diagnoseberichte mit Platzhaltern. "
        "Nutze die ausstehende Aktion 'Diagnosebericht erstellen', damit ich reale Home-Assistant- "
        "und EcoFlow-Daten abrufe und lokal als Markdown-Datei speichere."
    )


def _handle_priority_feedback(message: str) -> dict[str, Any] | None:
    command = _strip_wake_prefix(message).strip(" .!?,:")
    normalized = command.lower()

    rule: tuple[str, str, str, str] | None = None
    if "lotto24" in normalized and ("unwichtig" in normalized or "werbung" in normalized):
        rule = ("lotto24", "low", "marketing", "Lotto- und Jackpot-Werbung ist nicht wichtig.")
    elif "dreame" in normalized and ("werbung" in normalized or "unwichtig" in normalized):
        rule = ("dreame", "low", "marketing", "Produktwerbung ist nicht wichtig.")
    elif "linkedin" in normalized and ("mittel" in normalized or "medium" in normalized):
        rule = ("linkedin", "medium", "job", "LinkedIn-Jobs sind potenziell relevant, aber nicht kritisch.")
    elif "fernakademie" in normalized and "wichtig" in normalized:
        rule = ("fernakademie", "high", "academy", "Fernakademie-Nachrichten sind fuer den Nutzer wichtig.")
    elif "github" in normalized and "wichtig" in normalized:
        rule = ("github", "high", "security", "GitHub-Sicherheits- und Kontoereignisse sind wichtig.")
    else:
        sender_match = re.search(r"absender\s+(.+?)\s+unwichtig", command, re.I)
        if sender_match:
            sender = sender_match.group(1).strip(" .!?,:")
            rule = (sender, "low", "marketing", f"{sender} wurde als unwichtig markiert.")
        high_match = re.search(r"priorisiere\s+absender\s+(.+?)\s+hoch", command, re.I)
        if high_match:
            sender = high_match.group(1).strip(" .!?,:")
            rule = (sender, "high", "unknown", f"{sender} wurde als hohe Prioritaet markiert.")

    if not rule:
        return None

    match, priority, category, reason = rule
    display_match = {"lotto24": "LOTTO24", "dreame": "Dreame", "linkedin": "LinkedIn", "github": "GitHub"}.get(
        match,
        match,
    )
    add_sender_rule(match, priority, category, reason)
    write_audit_log(
        "assistant_priority_feedback",
        {"match": match, "priority": priority, "category": category},
    )
    return {
        "mode": "rule_based",
        "tool": "priority_feedback",
        "answer": f"Ich habe {display_match} als {_priority_label(priority)} / {category} gespeichert.",
        "risk": ActionRisk.GREEN,
        "result": {
            "match": match.lower(),
            "priority": priority,
            "category": category,
            "reason": reason,
        },
    }


def _strip_wake_prefix(message: str) -> str:
    return re.sub(
        r"^\s*(?:hey\s+|okay\s+|ok\s+|hallo\s+|hammer\s+)?jarvis[\s,:-]*",
        "",
        message,
        flags=re.I,
    )


def _priority_label(priority: str) -> str:
    return {
        "critical": "kritische Prioritaet",
        "high": "hohe Prioritaet",
        "medium": "mittlere Prioritaet",
        "low": "niedrige Prioritaet",
        "info": "Info-Prioritaet",
    }.get(priority, priority)


def _handle_watcher_command(normalized: str) -> dict[str, Any] | None:
    if any(term in normalized for term in ("pruefe alles", "prÃ¼fe alles", "starte ueberwachung", "starte Ã¼berwachung")):
        result = WatcherController().run_once()
        return {
            "mode": "rule_based",
            "tool": "watchers_run",
            "answer": f"Ich habe die Ueberwachung geprueft. Neue Hinweise: {result['created_count']}.",
            "risk": ActionRisk.GREEN,
            "result": result,
        }
    if any(term in normalized for term in ("welche hinweise gibt es", "hast du warnungen", "zeige alerts")):
        alerts = WatcherController().list_alerts()
        if not alerts:
            answer = "Aktuell gibt es keine aktiven proaktiven Hinweise."
        else:
            lines = [f"Aktive Hinweise: {len(alerts)}"]
            for alert in alerts[:5]:
                lines.append(f"- {alert.get('title')}: {alert.get('message')}")
            answer = "\n".join(lines)
        return {
            "mode": "rule_based",
            "tool": "watchers_alerts",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "result": {"alerts": alerts},
        }
    return None


def _format_event_time(event: dict[str, Any]) -> str:
    return event["start"][11:16] if "T" in event.get("start", "") else "GanztÃ¤gig"



