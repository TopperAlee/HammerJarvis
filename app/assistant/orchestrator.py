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
from app.assistant.knowledge.context_builder import relevant_knowledge_context
from app.assistant.knowledge.knowledge_store import KnowledgeStore
from app.assistant.llm_client import LLMClient, sanitize_identity_response
from app.assistant.memory.memory_classifier import MemoryClassifier, infer_memory_item
from app.assistant.memory.memory_formatter import format_memory_added, format_memory_list
from app.assistant.memory.memory_retriever import relevant_memory_context
from app.assistant.memory.memory_store import MemoryStore
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
from hammer_jarvis.query.engine import EngineeringQueryEngine, EngineeringQueryError
from hammer_jarvis.query.models import EngineeringQueryRequest, EngineeringQueryType
from hammer_jarvis.query.parser import EngineeringQueryParser
from hammer_jarvis.understanding.engine import EngineeringUnderstandingEngine


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
        memory_response = self._handle_memory_command(message, normalized)
        if memory_response:
            return memory_response
        knowledge_response = self._handle_knowledge_command(message, normalized)
        if knowledge_response:
            return knowledge_response
        priority_feedback = _handle_priority_feedback(message)
        if priority_feedback:
            return priority_feedback
        watcher_response = _handle_watcher_command(normalized)
        if watcher_response:
            return watcher_response
        file_action_response = self._handle_file_result_action(normalized)
        if file_action_response:
            return file_action_response
        action_response = self._handle_action_command(normalized)
        if action_response:
            return action_response
        engineering_query_response = self._handle_engineering_query_command(message)
        if engineering_query_response:
            return engineering_query_response
        ha_allowlist_response = self._handle_home_assistant_allowlist_query(normalized)
        if ha_allowlist_response:
            return ha_allowlist_response
        ha_entity_catalog_response = self._handle_home_assistant_entity_catalog_command(message, normalized)
        if ha_entity_catalog_response:
            return ha_entity_catalog_response
        ha_control_response = self._handle_home_assistant_control_command(message, normalized)
        if ha_control_response:
            return ha_control_response
        ha_allowlist_manage_response = self._handle_home_assistant_allowlist_management(normalized)
        if ha_allowlist_manage_response:
            return ha_allowlist_manage_response
        ha_action_response = self._handle_home_assistant_action_command(normalized)
        if ha_action_response:
            return ha_action_response
        skill_response = self._handle_skill_command(message, normalized)
        if skill_response:
            return skill_response
        web_response = self._handle_web_research_command(message, normalized)
        if web_response:
            return web_response
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
        memory_context = relevant_memory_context(message)
        knowledge_context = relevant_knowledge_context(message)
        context_blocks = []
        if memory_context:
            context_blocks.append(f"Persoenliches Gedaechtnis:\n{memory_context}")
        if knowledge_context["context"]:
            context_blocks.append(knowledge_context["context"])
        user_content = "\n\n".join([*context_blocks, f"Nutzerfrage: {message}"])
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
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
                "knowledge_sources": knowledge_context["sources"],
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
            "knowledge_sources": knowledge_context["sources"],
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
            actions = pending_action_store.present_actions(pending_action_store.list_pending_actions(), source="actions_pending")
            return {
                "mode": "rule_based",
                "tool": "actions_pending",
                "answer": _format_pending_actions(actions),
                "risk": ActionRisk.GREEN,
                "result": {"actions": actions, "count": len(actions)},
            }
        if _is_plural_action_confirmation(normalized):
            actions = pending_action_store.get_active_presented_actions()
            if len(actions) == 1:
                return _action_ambiguous_response(
                    f"Meinst du Aktion 1: {actions[0].get('title', '')}? Sage 'Bestätige Aktion 1'."
                )
            if len(actions) > 1:
                return _action_ambiguous_response("Bitte nenne die genaue Aktionsnummer, z. B. 'Bestätige Aktion 2'.")
            return _action_ambiguous_response("Ich kann diese Bestätigung nicht eindeutig zuordnen. Bitte zeige die offenen Aktionen erneut an.")
        if _is_bare_action_confirmation(normalized):
            action = pending_action_store.resolve_single_presented_action()
            if action == "ambiguous":
                return _action_ambiguous_response("Bitte sag, welche Aktion ich ausführen soll, zum Beispiel: 'Bestätige Aktion 1'.")
            if action is None:
                return _action_ambiguous_response("Ich kann diese Bestätigung nicht eindeutig zuordnen. Bitte zeige die offenen Aktionen erneut an.")
            result = ActionExecutor(registry=self.registry).execute(action["id"], confirm=True)
            return {
                "mode": "rule_based",
                "tool": "action_execute",
                "answer": _format_action_execution_answer(result),
                "risk": ActionRisk.GREEN,
                "result": result,
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
        if action is None and (_is_action_execute_intent(normalized) or _is_action_confirm_intent(normalized)):
            return _action_ambiguous_response(f"Ich kann Aktion {_action_index(normalized) or 1} nicht eindeutig zuordnen. Bitte zeige die offenen Aktionen erneut an.")
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

    def _handle_engineering_query_command(self, original: str) -> dict[str, Any] | None:
        parsed = EngineeringQueryParser().parse(original)
        if parsed.query_type == EngineeringQueryType.UNKNOWN:
            return None
        try:
            request = EngineeringQueryRequest(query=original)
            engine = _engineering_query_engine_for_chat()
            result = engine.execute(request)
            _save_engineering_query_context(request, result)
        except EngineeringQueryError as exc:
            return {
                "mode": "engineering_query",
                "tool": "engineering.query",
                "answer": str(exc),
                "risk": ActionRisk.GREEN,
                "result": {
                    "query": original,
                    "query_type": parsed.query_type.value,
                    "status": "ERROR",
                    "error_code": f"HTTP_{exc.status_code}",
                    "statistics": {"read_only": True},
                },
            }
        payload = result.model_dump()
        return {
            "mode": "engineering_query",
            "tool": "engineering.query",
            "answer": result.answer,
            "risk": ActionRisk.GREEN,
            "query_type": result.query_type.value,
            "status": result.status,
            "error_code": result.error_code,
            "result": payload,
        }

    def _handle_memory_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        if _is_memory_store_command(normalized):
            text_to_store = _extract_memory_store_text(original)
            classification = MemoryClassifier().classify_text(text_to_store)
            if classification.get("blocked"):
                return {
                    "mode": "rule_based",
                    "tool": "memory_add",
                    "answer": classification["message"],
                    "risk": ActionRisk.GREEN,
                    "blocked": True,
                    "result": classification,
                }
            item = MemoryStore().add_memory(infer_memory_item(text_to_store))
            return {
                "mode": "rule_based",
                "tool": "memory_add",
                "answer": format_memory_added(item),
                "risk": ActionRisk.GREEN,
                "result": item,
            }
        if _is_memory_recall_command(normalized):
            query = _extract_memory_query(original)
            result = MemoryStore().search_memory(query, limit=10)
            return {
                "mode": "rule_based",
                "tool": "memory_search",
                "answer": format_memory_list(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if _is_memory_forget_command(normalized):
            query = _extract_memory_forget_query(original)
            matches = MemoryStore().search_memory(query, limit=1).get("memories", [])
            if not matches:
                return {"mode": "rule_based", "tool": "memory_delete", "answer": "Ich habe keine passende Erinnerung gefunden.", "risk": ActionRisk.GREEN, "result": {"deleted": False}}
            result = MemoryStore().delete_memory(matches[0]["id"])
            return {"mode": "rule_based", "tool": "memory_delete", "answer": "Ich habe die Erinnerung gelöscht.", "risk": ActionRisk.GREEN, "result": result}
        if _is_ambiguous_correction(normalized):
            text_to_store = _extract_correction_text(original)
            action = pending_action_store.create_action(
                {
                    "title": "Memory-Vorschlag speichern",
                    "description": "Korrektur als lokale Erinnerung speichern.",
                    "tool_name": "memory_add",
                    "arguments": {"item": infer_memory_item(text_to_store)},
                    "risk": ActionRisk.YELLOW,
                    "source": "memory_suggestion",
                    "requires_confirmation": True,
                }
            )
            presented_actions = pending_action_store.present_actions([action], source="memory_suggestion")
            return {
                "mode": "rule_based",
                "tool": "memory_suggestion",
                "answer": f"Soll ich mir merken, dass {text_to_store.strip(' .')}?",
                "risk": ActionRisk.GREEN,
                "pending_actions": presented_actions,
                "result": {"suggested": infer_memory_item(text_to_store)},
            }
        return None

    def _handle_knowledge_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        if _is_knowledge_search_command(normalized):
            query = _extract_knowledge_search_query(original)
            result = KnowledgeStore().search_knowledge(query, limit=8)
            return {
                "mode": "rule_based",
                "tool": "knowledge_search",
                "answer": _format_knowledge_search_answer(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if _is_knowledge_documents_command(normalized):
            result = KnowledgeStore().list_documents()
            return {
                "mode": "rule_based",
                "tool": "knowledge_documents",
                "answer": _format_knowledge_documents_answer(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        return None

    def _handle_home_assistant_allowlist_query(self, normalized: str) -> dict[str, Any] | None:
        if not _is_home_assistant_allowlist_query(normalized):
            return None
        executed = self.registry.execute_tool("home_assistant_list_allowed_actions", {}, confirm=False)
        result = executed.get("result", {})
        return {
            "mode": "rule_based",
            "tool": "home_assistant_list_allowed_actions",
            "executed_tool": "home_assistant_list_allowed_actions",
            "answer": _format_home_assistant_allowed_actions(result),
            "risk": ActionRisk.GREEN,
            "result": result,
        }

    def _handle_home_assistant_entity_catalog_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        route = _home_assistant_entity_catalog_route(original, normalized)
        if not route:
            return None
        tool_name, arguments = route
        executed = self.registry.execute_tool(tool_name, arguments, confirm=False)
        result = executed.get("result", {})
        return {
            "mode": "rule_based",
            "tool": tool_name,
            "executed_tool": tool_name,
            "answer": _format_home_assistant_entity_catalog(tool_name, result),
            "risk": ActionRisk.GREEN,
            "result": result,
        }

    def _handle_home_assistant_control_command(self, original: str, normalized: str) -> dict[str, Any] | None:
        if not _is_home_assistant_control_intent(normalized):
            return None
        resolved = self.registry.run("home_assistant_resolve_control_intent", command=original)
        if resolved.get("blocked") and resolved.get("reason") == "entity_not_found":
            return None
        if resolved.get("ambiguous"):
            return {
                "mode": "rule_based",
                "tool": "home_assistant_resolve_control_intent",
                "answer": _format_ha_control_ambiguous(resolved),
                "risk": ActionRisk.GREEN,
                "result": resolved,
            }
        if resolved.get("blocked"):
            return {
                "mode": "rule_based",
                "tool": "home_assistant_resolve_control_intent",
                "answer": str(resolved.get("message") or f"Diese Aktion ist blockiert: {resolved.get('reason')}"),
                "risk": ActionRisk.GREEN,
                "result": resolved,
            }
        if resolved.get("auto_execute"):
            executed = self.registry.execute_tool(
                "home_assistant_execute_control_action",
                {
                    "entity_id": resolved.get("entity_id"),
                    "action": resolved.get("action"),
                    "parameters": resolved.get("parameters", {}),
                    "source_command": original,
                },
                confirm=True,
            )
            result = executed.get("result", executed)
            return {
                "mode": "rule_based",
                "tool": "home_assistant_execute_control_action",
                "executed_tool": "home_assistant_execute_control_action",
                "answer": _format_ha_control_auto_executed(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        if resolved.get("batch"):
            action = pending_action_store.create_action(
                {
                    "title": str(resolved.get("title") or "Home-Assistant-Batch-Aktion"),
                    "description": str(resolved.get("warning") or "Batch-Steueraktion. Ausführung erst nach Bestätigung."),
                    "tool_name": "home_assistant_execute_batch_action",
                    "arguments": {"actions": resolved.get("actions", [])},
                    "risk": resolved.get("risk", "YELLOW"),
                    "source": "home_assistant_control_broker",
                    "requires_confirmation": True,
                }
            )
            presented_actions = pending_action_store.present_actions([action], source="smart_home")
            return {
                "mode": "rule_based",
                "tool": "home_assistant_prepare_batch_action",
                "answer": _format_ha_control_prepared(resolved, action),
                "risk": ActionRisk.GREEN,
                "result": resolved,
                "pending_actions": presented_actions,
            }
        action = pending_action_store.create_action(
            {
                "title": str(resolved.get("title") or "Home-Assistant-Aktion"),
                "description": str(resolved.get("warning") or "Steueraktion. Ausführung erst nach Bestätigung."),
                "tool_name": "home_assistant_execute_control_action",
                "arguments": {
                    "entity_id": resolved.get("entity_id"),
                    "action": resolved.get("action"),
                    "parameters": resolved.get("parameters", {}),
                },
                "risk": resolved.get("risk", "YELLOW"),
                "source": "home_assistant_control_broker",
                "requires_confirmation": True,
            }
        )
        presented_actions = pending_action_store.present_actions([action], source="smart_home")
        return {
            "mode": "rule_based",
            "tool": "home_assistant_prepare_control_action",
            "answer": _format_ha_control_prepared(resolved, action),
            "risk": ActionRisk.GREEN,
            "result": resolved,
            "pending_actions": presented_actions,
        }

    def _handle_home_assistant_allowlist_management(self, normalized: str) -> dict[str, Any] | None:
        if _is_home_assistant_discovery_query(normalized):
            executed = self.registry.execute_tool("home_assistant_discover_actionable_entities", {}, confirm=False)
            result = executed.get("result", {})
            return {
                "mode": "rule_based",
                "tool": "home_assistant_discover_actionable_entities",
                "executed_tool": "home_assistant_discover_actionable_entities",
                "answer": _format_home_assistant_action_candidates(result),
                "risk": ActionRisk.GREEN,
                "result": result,
            }
        parsed = _parse_home_assistant_allowlist_change(normalized)
        if not parsed:
            return None
        if parsed["mode"] == "remove":
            allowed = self.registry.run("home_assistant_list_allowed_actions")
            candidate = _find_candidate(allowed.get("allowed_entities", []), parsed["target"])
        else:
            discovery = self.registry.run("home_assistant_discover_actionable_entities")
            candidate = _find_candidate(discovery.get("candidates", []), parsed["target"])
        if not candidate:
            return {
                "mode": "rule_based",
                "tool": "home_assistant_allowlist_prepare",
                "answer": "Ich habe keine sichere passende Entity gefunden. Ich habe nichts freigegeben und nichts geschaltet.",
                "risk": ActionRisk.GREEN,
                "result": {"blocked": True, "reason": "candidate_not_found"},
            }
        tool_name = "home_assistant_add_to_allowlist" if parsed["mode"] == "add" else "home_assistant_remove_from_allowlist"
        arguments = (
            {
                "entity_id": candidate["entity_id"],
                "friendly_name": candidate.get("friendly_name") or candidate["entity_id"],
                "domain": candidate.get("domain") or str(candidate["entity_id"]).split(".", 1)[0],
                "allowed_actions": candidate.get("suggested_actions") or candidate.get("allowed_actions") or ["turn_on", "turn_off"],
            }
            if parsed["mode"] == "add"
            else {"entity_id": candidate["entity_id"]}
        )
        title = (
            f"{candidate.get('friendly_name') or candidate['entity_id']} zur Smart-Home-Freigabe hinzufügen"
            if parsed["mode"] == "add"
            else f"{candidate.get('friendly_name') or candidate['entity_id']} aus Smart-Home-Freigabe entfernen"
        )
        action = pending_action_store.create_action(
            {
                "title": title,
                "description": "Änderung an der Smart-Home-Freigabe. Ausführung erst nach Bestätigung.",
                "tool_name": tool_name,
                "arguments": arguments,
                "risk": ActionRisk.YELLOW,
                "source": "home_assistant_allowlist",
                "requires_confirmation": True,
            }
        )
        presented_actions = pending_action_store.present_actions([action], source="home_assistant_allowlist")
        write_audit_log("assistant_action_proposed", {"tool": tool_name, "risk": ActionRisk.YELLOW, "action_id": action["id"]})
        verb = "hinzufügen" if parsed["mode"] == "add" else "entfernen"
        answer = (
            f"Ich kann {candidate.get('friendly_name') or candidate['entity_id']} zur Smart-Home-Freigabe {verb}. "
            "Diese Änderung benötigt Bestätigung.\nSag: 'Bestätige Aktion 1'."
        )
        return {
            "mode": "rule_based",
            "tool": "home_assistant_allowlist_prepare",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "result": {"candidate": candidate, "mode": parsed["mode"]},
            "pending_actions": presented_actions,
        }

    def _handle_home_assistant_action_command(self, normalized: str) -> dict[str, Any] | None:
        parsed = _parse_home_assistant_action_intent(normalized)
        if not parsed:
            return None
        prepare_result = self.registry.run(
            "home_assistant_prepare_action",
            entity_name_or_id=parsed["target"],
            action=parsed["action"],
        )
        if prepare_result.get("blocked"):
            return {
                "mode": "rule_based",
                "tool": "home_assistant_prepare_action",
                "answer": "Diese Aktion ist nicht freigegeben. Ich schalte keine nicht erlaubten Geräte.",
                "risk": ActionRisk.GREEN,
                "result": prepare_result,
            }
        action = pending_action_store.create_action(
            {
                "title": str(prepare_result.get("title") or "Home-Assistant-Aktion ausführen"),
                "description": "Freigegebene Smart-Home-Aktion. Ausführung erst nach Bestätigung.",
                "tool_name": "home_assistant_execute_action",
                "arguments": {
                    "entity_id": prepare_result.get("entity_id"),
                    "action": prepare_result.get("action"),
                },
                "risk": ActionRisk.YELLOW,
                "source": "home_assistant_action",
                "requires_confirmation": True,
            }
        )
        presented_actions = pending_action_store.present_actions([action], source="smart_home")
        write_audit_log(
            "assistant_action_proposed",
            {"tool": "home_assistant_execute_action", "risk": ActionRisk.YELLOW, "action_id": action["id"]},
        )
        answer = (
            f"Ich kann {prepare_result.get('title')}. Diese Aktion benötigt Bestätigung.\n"
            "Sag: 'Bestätige Aktion 1'."
        )
        return {
            "mode": "rule_based",
            "tool": "home_assistant_prepare_action",
            "answer": answer,
            "risk": ActionRisk.GREEN,
            "result": prepare_result,
            "pending_actions": presented_actions,
        }

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


def _engineering_query_engine_for_chat() -> EngineeringQueryEngine:
    import app.main as main_module

    graph = main_module._understanding_source_graph()
    if main_module._understanding_report is None:
        report = EngineeringUnderstandingEngine().build(
            graph,
            diagnostics=main_module._diagnostic_report_store.get_latest(),
            documents=main_module._document_store.list(),
            knowledge_documents=main_module._knowledge_documents_for_understanding(),
        )
        main_module._understanding_report = report
        main_module._understanding_object_store = main_module._build_understanding_object_store(graph, report)
    return EngineeringQueryEngine(
        graph=graph,
        understanding=main_module._understanding_report,
        objects=main_module._understanding_object_store,
        diagnostics=main_module._diagnostic_report_store.get_latest(),
        documents=main_module._document_store.list(),
    )


def _save_engineering_query_context(request: EngineeringQueryRequest, result: Any) -> None:
    import app.main as main_module

    main_module._engineering_query_store.save(request, result)
    matches = getattr(result, "matched_objects", []) or []
    best_object = matches[0].object_id if matches else None
    main_module._intent_context_store.update(
        {
            "last_intent": "engineering.query",
            "last_search_query": request.query,
            "last_selected_node": best_object,
            "current_task": "engineering.query",
        }
    )


def _parse_home_assistant_action_intent(message: str) -> dict[str, str] | None:
    folded = _fold_german_text(message)
    if "szene" in folded and any(term in folded for term in ("aktivieren", "aktiviere", "einschalten", "an")):
        target = _cleanup_home_assistant_target(folded, ("aktiviere", "aktivieren", "szene"))
        return {"target": target or folded, "action": "turn_on"}
    explicit_control_intent = any(term in folded for term in ("schalte", "mach", "licht", "steckdose"))
    if not explicit_control_intent:
        return None
    if _is_unsafe_home_assistant_action_text(folded):
        return {"target": folded, "action": "blocked"}
    action = ""
    if any(term in folded for term in (" aus", "ausschalten", "mach aus", "licht aus", "steckdose aus")):
        action = "turn_off"
    elif any(term in folded for term in (" ein", " an", "einschalten", "anschalten", "mach an", "licht an", "steckdose an")):
        action = "turn_on"
    if not action:
        return None
    target = _cleanup_home_assistant_target(
        folded,
        (
            "schalte",
            "mach",
            "bitte",
            "die",
            "das",
            "den",
            "ein",
            "an",
            "aus",
            "einschalten",
            "anschalten",
            "ausschalten",
        ),
    )
    if not target:
        if "licht" in folded:
            target = "licht"
        elif "steckdose" in folded:
            target = "steckdose"
    return {"target": target, "action": action} if target else None


def _is_home_assistant_allowlist_query(message: str) -> bool:
    folded = _fold_german_text(message).replace("-", " ")
    return any(
        term in folded
        for term in (
            "welche smart home aktionen sind freigegeben",
            "welche smarthome aktionen sind freigegeben",
            "was darfst du schalten",
            "welche geraete darfst du schalten",
            "welche gerate darfst du schalten",
            "welche home assistant aktionen sind erlaubt",
            "zeige allowlist",
            "zeige freigegebene geraete",
            "zeige freigegebene gerate",
            "freigegebene smart home aktionen",
        )
    )


def _is_home_assistant_discovery_query(message: str) -> bool:
    folded = _fold_german_text(message).replace("-", " ")
    return any(
        term in folded
        for term in (
            "zeige schaltbare geraete",
            "zeige schaltbare gerate",
            "zeige lichtgeraete",
            "zeige lichtgerate",
            "welche geraete kann ich freigeben",
            "welche gerate kann ich freigeben",
            "welche smart home geraete sind sicher",
            "welche smart home gerate sind sicher",
        )
    )


def _parse_home_assistant_allowlist_change(message: str) -> dict[str, str] | None:
    folded = _fold_german_text(message)
    if "freigabe" in folded and any(term in folded for term in ("entferne", "entfernen")):
        target = _cleanup_home_assistant_target(folded, ("entferne", "entfernen", "aus", "der", "die", "das", "freigabe"))
        return {"mode": "remove", "target": target} if target else None
    if any(term in folded for term in ("gib", "erlaube", "fuege", "fuge")) and any(
        term in folded for term in ("frei", "freigabe", "erlaube", "hinzu")
    ):
        target = _cleanup_home_assistant_target(
            folded,
            ("gib", "erlaube", "fuege", "fuge", "zur", "freigabe", "hinzu", "frei", "der", "die", "das"),
        )
        return {"mode": "add", "target": target} if target else None
    return None


def _format_home_assistant_allowed_actions(result: dict[str, Any]) -> str:
    entities = list(result.get("allowed_entities") or [])
    scenes = list(result.get("allowed_scenes") or [])
    if not entities and not scenes:
        return "\n".join(
            [
                "Aktuell sind keine Smart-Home-Aktionen freigegeben.",
                "Ich schalte deshalb keine Geräte.",
                "Trage erlaubte Geräte in app/config/home_assistant_action_allowlist.json ein.",
                "",
                "Alle Smart-Home-Aktionen benötigen vor der Ausführung eine Bestätigung.",
            ]
        )

    lines = ["Freigegebene Smart-Home-Aktionen:"]
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("friendly_name") or entity.get("entity_id") or "Unbekannt")
        entity_id = str(entity.get("entity_id") or "-")
        actions = ", ".join(_german_ha_action(action) for action in entity.get("allowed_actions", []))
        lines.append(f"- {name} ({entity_id}): {actions or 'keine Aktion'}")
    for scene in scenes:
        if isinstance(scene, dict):
            name = str(scene.get("friendly_name") or scene.get("entity_id") or "Szene")
            entity_id = str(scene.get("entity_id") or "-")
        else:
            name = str(scene)
            entity_id = str(scene)
        lines.append(f"- {name} ({entity_id}): aktivieren")

    blocked = list(result.get("blocked_domains") or [])
    if blocked:
        lines.extend(["", "Blockierte Geräteklassen:"])
        for domain in blocked:
            lines.append(f"- {_german_blocked_domain(str(domain))}")
    lines.extend(["", "Alle Smart-Home-Aktionen benötigen vor der Ausführung eine Bestätigung."])
    return "\n".join(lines)


def _format_home_assistant_action_candidates(result: dict[str, Any]) -> str:
    candidates = list(result.get("candidates") or [])[:20]
    lines = ["Schaltbare Kandidaten:"]
    if not candidates:
        lines.append("- Keine sicheren Kandidaten gefunden.")
    for candidate in candidates:
        name = str(candidate.get("friendly_name") or candidate.get("entity_id") or "Unbekannt")
        entity_id = str(candidate.get("entity_id") or "-")
        actions = ", ".join(_german_ha_action(action) for action in candidate.get("suggested_actions", []))
        lines.append(f"- {name} ({entity_id}): {actions}")
    lines.extend(["", "Ich habe nichts freigegeben und nichts geschaltet."])
    return "\n".join(lines)


def _find_candidate(candidates: list[Any], target: str) -> dict[str, Any] | None:
    normalized_target = _normalize_plain(target)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        entity_id = _normalize_plain(str(item.get("entity_id", "")))
        friendly_name = _normalize_plain(str(item.get("friendly_name", "")))
        if normalized_target in {entity_id, friendly_name} or normalized_target in friendly_name:
            return item
    return None


def _german_ha_action(action: Any) -> str:
    return {
        "turn_on": "einschalten",
        "turn_off": "ausschalten",
    }.get(str(action), str(action))


def _german_blocked_domain(domain: str) -> str:
    return {
        "lock": "Schlösser",
        "alarm_control_panel": "Alarmanlagen",
        "cover": "Türen, Garagen und Abdeckungen",
        "climate": "Heizung und Klima",
        "fan": "Ventilatoren",
        "valve": "Ventile",
        "siren": "Sirenen",
        "camera": "Kameras",
    }.get(domain, domain)


def _normalize_plain(value: str) -> str:
    value = _fold_german_text(value)
    value = re.sub(r"[^a-z0-9_. ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_unsafe_home_assistant_action_text(message: str) -> bool:
    return any(
        term in message
        for term in (
            "lock",
            "schloss",
            "haustuer",
            "alarm",
            "heizung",
            "thermostat",
            "garage",
            "ofen",
            "herd",
            "pumpe",
            "sps",
            "plc",
        )
    )


def _cleanup_home_assistant_target(message: str, remove_tokens: tuple[str, ...]) -> str:
    target = message
    for token in remove_tokens:
        target = re.sub(rf"\b{re.escape(token)}\b", " ", target)
    target = re.sub(r"[^a-z0-9_. ]+", " ", target)
    return re.sub(r"\s+", " ", target).strip()


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
    return any(
        term in message
        for term in (
            "was schlaegst du vor",
            "was schlÃ¤gst du vor",
            "welche aktionen stehen aus",
            "zeige aktionen",
            "zeige offene aktionen",
            "offene aktionen",
            "welche aktionen sind offen",
        )
    )


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


def _is_bare_action_confirmation(message: str) -> bool:
    folded = _fold_german_text(message)
    return folded in {"ja", "ja bestaetigen", "bestaetigen", "bestatigen", "ok", "okay", "mach es"}


def _is_plural_action_confirmation(message: str) -> bool:
    folded = _fold_german_text(message)
    return any(
        term in folded
        for term in (
            "bestaetige aktionen",
            "bestatige aktionen",
            "bestaetige alle aktionen",
            "bestatige alle aktionen",
            "fuehr alle aktionen aus",
            "fuehre alle aktionen aus",
        )
    )


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
    normalized_message = _normalize_action_reference(message)
    if normalized_message and not normalized_message.isdigit():
        matched = _pending_action_by_title(normalized_message)
        if matched:
            return matched
    index = _action_index(message)
    if index is not None:
        action = _pending_action_by_index(index)
        if action:
            return action
    if not normalized_message:
        return None
    return _pending_action_by_title(normalized_message)


def _pending_action_by_title(normalized_message: str) -> dict[str, Any] | None:
    for action in pending_action_store.list_pending_actions():
        title = _normalize_action_reference(str(action.get("title") or ""))
        if title and _action_reference_matches(title, normalized_message):
            return action
    return None


def _action_reference_matches(title: str, message: str) -> bool:
    if title == message:
        return True
    title_tokens = set(title.split())
    message_tokens = set(message.split())
    if len(title_tokens) >= 2 and title_tokens.issubset(message_tokens):
        return True
    if len(message_tokens) >= 2 and message_tokens.issubset(title_tokens):
        return True
    return False


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
    return pending_action_store.resolve_presented_action(index)


def _action_not_found_response() -> dict[str, Any]:
    return {
        "mode": "rule_based",
        "tool": "action_execute",
        "answer": "Diese Aktion ist nicht mehr ausstehend oder wurde nicht gefunden.",
        "risk": ActionRisk.GREEN,
        "result": {"error": True},
    }


def _action_ambiguous_response(message: str) -> dict[str, Any]:
    return {
        "mode": "rule_based",
        "tool": "action_execute",
        "answer": message,
        "risk": ActionRisk.GREEN,
        "result": {"error": True, "ambiguous": True},
    }


def _append_pending_actions(answer: str, actions: list[dict[str, Any]]) -> str:
    if not actions:
        return answer
    actions = pending_action_store.present_actions(actions, source=str(actions[0].get("source") or "chat"))
    return "\n\n".join([answer, _format_pending_actions(actions), "Sag: 'Führe Aktion 1 aus.'"])


def _format_pending_actions(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "Es stehen aktuell keine Aktionen aus."
    lines = ["Mögliche nächste Aktionen:"]
    for index, action in enumerate(actions[:3], start=1):
        display_index = action.get("display_index") or index
        lines.append(f"{display_index}. [{_risk_label(str(action.get('risk', 'GREEN')))}] {action.get('title')}")
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
        if isinstance(tool_result, dict) and (tool_result.get("added") or tool_result.get("updated")):
            actions = ", ".join(_german_ha_action(action) for action in tool_result.get("allowed_actions", []))
            return (
                f"{tool_result.get('friendly_name') or tool_result.get('entity_id')} wurde zur Smart-Home-Freigabe hinzugefügt.\n"
                f"Aktionen: {actions}.\n"
                "Trotz Freigabe braucht jede Ausführung weiterhin Bestätigung."
            )
        if isinstance(tool_result, dict) and "removed" in tool_result:
            return str(tool_result.get("message") or "Entity wurde aus der Smart-Home-Freigabe entfernt.")
        if isinstance(tool_result, dict) and tool_result.get("message"):
            return f"Ausgeführt: {title}\n\n{tool_result.get('message')}"
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


def _home_assistant_entity_catalog_route(
    original: str,
    normalized: str,
) -> tuple[str, dict[str, Any]] | None:
    if "synchronisiere home assistant entities" in normalized or "sync home assistant entities" in normalized:
        return "home_assistant_sync_entities", {"force": True}
    if "welche geraete kann ich freigeben" in normalized or "welche geräte kann ich freigeben" in normalized:
        return "home_assistant_list_actionable_candidates", {"limit": 100}
    if "freigabe-kandidaten" in normalized or "freigabe kandidaten" in normalized:
        return "home_assistant_list_actionable_candidates", {"limit": 100}
    domain_alias = _read_only_domain_alias(normalized)
    if domain_alias:
        return "home_assistant_list_entities", {"domain": domain_alias, "state": None, "limit": 100}
    if "welche geraete sind unavailable" in normalized or "welche geräte sind unavailable" in normalized:
        return "home_assistant_list_unavailable_entities", {"limit": 100}
    if "home assistant" in normalized and "unavailable" in normalized:
        return "home_assistant_list_unavailable_entities", {"limit": 100}
    entity_match = re.search(r"(?:details zu|entity details zu|zeige details zu)\s+([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)", original, re.I)
    if entity_match:
        return "home_assistant_get_entity", {"entity_id": entity_match.group(1)}
    if "suche" in normalized and "home assistant" in normalized:
        return "home_assistant_search_entities", {"query": _extract_ha_search_query(original), "domain": None, "limit": 50}
    if "finde entität" in normalized or "finde entitaet" in normalized or "finde entity" in normalized:
        return "home_assistant_search_entities", {"query": _extract_after_any(original, ("finde Entität", "finde Entitaet", "finde Entity")), "domain": None, "limit": 50}
    return None


def _is_home_assistant_control_intent(message: str) -> bool:
    if "freigabe" in message or "was macht ecoflow" in message:
        return False
    control_terms = (
        "schalte",
        "einschalten",
        "ausschalten",
        "licht an",
        "licht aus",
        "alle lichter",
        "starte szene",
        "aktiviere",
        "deaktivieren",
        "temperatur",
        "rollladen",
        "öffnen",
        "oeffnen",
        "schließen",
        "schliessen",
    )
    return any(term in message for term in control_terms) or bool(re.search(r"\bmach\b.+\b(an|aus)\b", message)) or bool(re.search(r"\b\d+(?:[,.]\d+)?\s*grad\b", message))


def _read_only_domain_alias(message: str) -> str | None:
    if not any(term in message for term in ("zeige", "liste", "welche", "alle", "gibt es")):
        return None
    aliases = (
        (("heizungen", "thermostate", "climate entities", "klima"), "climate"),
        (("lichter", "lichtgeräte", "lichtgeraete"), "light"),
        (("switches", "schalter", "steckdosen", "smartsteckdosen"), "switch"),
        (("rollläden", "rolllaeden", "rollladen"), "cover"),
        (("szenen",), "scene"),
        (("automationen",), "automation"),
        (("skripte",), "script"),
    )
    for terms, domain in aliases:
        if any(term in message for term in terms):
            return domain
    return None


def _is_memory_store_command(message: str) -> bool:
    return any(message.startswith(prefix) for prefix in ("merke dir", "speichere", "für die zukunft", "fuer die zukunft", "ab jetzt gilt", "das ist wichtig"))


def _is_memory_recall_command(message: str) -> bool:
    return any(prefix in message for prefix in ("was weißt du über", "was weisst du ueber", "was weisst du über", "was hast du dir", "zeige dein gedächtnis", "zeige dein gedaechtnis"))


def _is_memory_forget_command(message: str) -> bool:
    return message.startswith("vergiss") or "lösche aus deinem gedächtnis" in message or "loesche aus deinem gedaechtnis" in message or "entferne die erinnerung" in message


def _is_knowledge_search_command(message: str) -> bool:
    return any(
        term in message
        for term in (
            "suche im wissensspeicher",
            "was weißt du aus meinen dokumenten",
            "was weisst du aus meinen dokumenten",
            "wissensspeicher nach",
        )
    )


def _is_knowledge_documents_command(message: str) -> bool:
    return any(term in message for term in ("welche dokumente kennst du", "zeige wissensspeicher dokumente"))


def _is_ambiguous_correction(message: str) -> bool:
    return message.startswith("nein,") and " ist " in message


def _extract_memory_store_text(original: str) -> str:
    cleaned = _strip_wake_prefix(original).strip()
    cleaned = re.sub(r"^(merke dir,\s*dass|merke dir dass|merke dir|speichere,\s*dass|speichere dass|speichere|für die zukunft:|fuer die zukunft:|ab jetzt gilt:|das ist wichtig:)\s*", "", cleaned, flags=re.I)
    return cleaned.strip(" .!?:,")


def _extract_memory_query(original: str) -> str:
    cleaned = _strip_wake_prefix(original).strip()
    cleaned = re.sub(r"^(was weißt du über|was weisst du ueber|was weisst du über|zeige dein gedächtnis zu|zeige dein gedaechtnis zu)\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^was hast du dir\s+über\s+(.+?)\s+gemerkt\??$", r"\1", cleaned, flags=re.I)
    return cleaned.strip(" .!?:,")


def _extract_memory_forget_query(original: str) -> str:
    cleaned = _strip_wake_prefix(original).strip()
    cleaned = re.sub(r"^(vergiss|lösche aus deinem gedächtnis|loesche aus deinem gedaechtnis|entferne die erinnerung)\s*", "", cleaned, flags=re.I)
    return cleaned.strip(" .!?:,")


def _extract_knowledge_search_query(original: str) -> str:
    cleaned = _strip_wake_prefix(original).strip(" .!?:,")
    patterns = (
        r"^suche im wissensspeicher nach\s+",
        r"^was wei(?:ß|ss)t du aus meinen dokumenten (?:über|ueber)\s+",
        r"^wissensspeicher nach\s+",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)
    return cleaned.strip(" .!?:,")


def _extract_correction_text(original: str) -> str:
    return re.sub(r"^nein,\s*", "", _strip_wake_prefix(original).strip(), flags=re.I)


def _format_ha_control_prepared(prepared: dict[str, Any], action: dict[str, Any]) -> str:
    risk = str(prepared.get("risk", "YELLOW"))
    lines = [
        f"Ich kann {prepared.get('title', 'die Home-Assistant-Aktion vorbereiten')}.",
        f"Risiko: {_risk_label(risk)}",
    ]
    if prepared.get("warning"):
        lines.append(f"Warnung: {prepared['warning']}")
    if risk == "ORANGE" and not prepared.get("warning"):
        lines.append("Warnung: Diese Aktion kann Komfort, Energieverbrauch oder mechanische Bewegung beeinflussen.")
    lines.extend(
        [
            "Diese Aktion benötigt Bestätigung.",
            "Sag: 'Bestätige Aktion 1'.",
        ]
    )
    return "\n".join(lines)


def _format_ha_control_auto_executed(result: dict[str, Any]) -> str:
    if result.get("blocked"):
        return str(result.get("message") or "Nicht ausgeführt: Diese Geräteklasse ist blockiert.")
    title = str(result.get("title") or result.get("entity_id") or "Smart-Home-Aktion")
    action = str(result.get("action") or "")
    parameters = result.get("parameters") if isinstance(result.get("parameters"), dict) else {}
    if action == "set_temperature" and "temperature" in parameters:
        answer = f"Ausgeführt: {title.replace(' Temperatur setzen', '')} auf {float(parameters['temperature']):g} °C gesetzt."
    elif action == "turn_on":
        answer = f"Ausgeführt: {title.replace(' einschalten', '')} eingeschaltet."
    elif action == "turn_off":
        answer = f"Ausgeführt: {title.replace(' ausschalten', '')} ausgeschaltet."
    else:
        answer = f"Ausgeführt: {title}."
    if result.get("auto_execute"):
        answer += "\nAuto-Ausführung gemäß Smart-Home-Policy."
    return answer


def _format_ha_control_ambiguous(result: dict[str, Any]) -> str:
    heating = str(result.get("message") or "").lower().startswith("ich habe mehrere passende heizungen")
    lines = ["Ich habe mehrere passende Heizungen gefunden:" if heating else "Ich habe mehrere passende Geräte gefunden:"]
    for index, entity in enumerate(result.get("candidates", [])[:10], start=1):
        lines.append(f"{index}. {entity.get('friendly_name') or entity.get('entity_id')} ({entity.get('entity_id')})")
    lines.append("Welche soll ich verwenden?" if heating else "Bitte sag genauer, welches Gerät ich vorbereiten soll.")
    return "\n".join(lines)


def _extract_ha_search_query(original: str) -> str:
    cleaned = _strip_wake_prefix(original).strip(" .!?:,")
    match = re.search(r"suche\s+(.+?)\s+in\s+home assistant", cleaned, re.I)
    if match:
        return match.group(1).strip(" .!?:,")
    match = re.search(r"suche\s+(.+)$", cleaned, re.I)
    if match:
        query = re.sub(r"\s+in\s+home assistant.*$", "", match.group(1), flags=re.I)
        return query.strip(" .!?:,")
    return cleaned


def _extract_after_any(original: str, markers: tuple[str, ...]) -> str:
    folded = _strip_wake_prefix(original)
    for marker in markers:
        index = folded.lower().find(marker.lower())
        if index >= 0:
            return folded[index + len(marker):].strip(" .!?:,")
    return folded.strip(" .!?:,")


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


def _format_home_assistant_entity_catalog(tool_name: str, result: dict[str, Any]) -> str:
    if tool_name == "home_assistant_sync_entities":
        return (
            f"Home-Assistant-Entity-Katalog synchronisiert: {result.get('entity_count', 0)} Entities. "
            f"Quelle: {result.get('source', 'unbekannt')}."
        )
    if tool_name == "home_assistant_list_actionable_candidates":
        lines = ["Potentiell freigebbare Kandidaten:"]
        entities = list(result.get("entities") or [])
        if not entities:
            return "Ich habe keine potenziell freigebbaren Home-Assistant-Entities gefunden."
        for entity in entities[:20]:
            lines.append(_format_entity_catalog_line(entity))
        if any(entity.get("domain") == "switch" for entity in entities):
            lines.append("")
            lines.append("Switches nur freigeben, wenn klar ist, dass sie ungefährlich sind.")
        lines.append("Der Katalog vergibt keine Schaltrechte. Freigabe und Ausführung bleiben bestätigungspflichtig.")
        return "\n".join(lines)
    if tool_name == "home_assistant_list_unavailable_entities":
        entities = list(result.get("entities") or [])
        if not entities:
            return "Ich habe keine unavailable Entities im Home-Assistant-Entity-Katalog gefunden."
        lines = ["Kritisch/unavailable:"]
        for entity in entities[:20]:
            lines.append(_format_entity_catalog_line(entity))
        return "\n".join(lines)
    if tool_name == "home_assistant_get_entity":
        if not result.get("found"):
            return str(result.get("message") or "Entity wurde nicht gefunden.")
        return "Entity-Details:\n" + _format_entity_catalog_line(result.get("entity") or {})
    entities = _sort_home_assistant_entities(list(result.get("entities") or []))
    if tool_name == "home_assistant_list_entities" and result.get("domain") == "climate":
        if not entities:
            return (
                "Ich habe keine Home-Assistant-Entities vom Typ climate gefunden.\n"
                "Temperatursensoren wie sensor.wohnzimmer_rechts_temperatur sind nur Messwerte und können nicht gesteuert werden.\n"
                "Bitte prüfe in Home Assistant, ob deine Tado-/Thermostat-Integration climate.* Entities bereitstellt."
            )
        lines = [f"Ich habe {result.get('count', len(entities))} Heizungs-/Thermostat-Entities gefunden:"]
        for entity in entities[:20]:
            lines.append(_format_climate_entity_line(entity))
        return "\n".join(lines)
    lines = [f"Ich habe {result.get('count', len(entities))} Home-Assistant-Entities gefunden:"]
    for entity in entities[:20]:
        lines.append(_format_entity_catalog_line(entity))
    if not entities:
        lines.append("- Keine passenden Entities gefunden.")
    if tool_name == "home_assistant_search_entities":
        lines.append("")
        lines.append("Für Heizungssteuerung sind nur climate.* Entities relevant.")
    return "\n".join(lines)


def _format_entity_catalog_line(entity: dict[str, Any]) -> str:
    friendly_name = entity.get("friendly_name") or entity.get("entity_id") or "-"
    entity_id = entity.get("entity_id") or "-"
    domain = entity.get("domain") or "-"
    state = entity.get("state") or "-"
    allowlisted = "ja" if entity.get("is_allowlisted") else "nein"
    return f"- {friendly_name} | {entity_id} | {domain} | {state} | freigegeben: {allowlisted}"


def _format_climate_entity_line(entity: dict[str, Any]) -> str:
    parts = [
        f"- {entity.get('friendly_name') or entity.get('entity_id') or '-'}",
        str(entity.get("entity_id") or "-"),
        f"Status: {entity.get('state') or '-'}",
    ]
    attributes = entity.get("attributes_summary") if isinstance(entity.get("attributes_summary"), dict) else {}
    current = entity.get("current_temperature", attributes.get("current_temperature"))
    target = entity.get("temperature", entity.get("target_temperature", attributes.get("temperature")))
    if current is not None:
        parts.append(f"aktuelle Temperatur: {current} °C")
    if target is not None:
        parts.append(f"Zieltemperatur: {target} °C")
    return " | ".join(parts)


def _sort_home_assistant_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {
        "climate": 0,
        "light": 1,
        "switch": 2,
        "cover": 3,
        "scene": 4,
        "media_player": 5,
        "remote": 6,
        "sensor": 7,
        "binary_sensor": 8,
    }
    return sorted(entities, key=lambda item: (order.get(str(item.get("domain")), 99), str(item.get("friendly_name") or item.get("entity_id"))))


def _format_knowledge_search_answer(result: dict[str, Any]) -> str:
    results = list(result.get("results") or [])
    if not results:
        return "Ich habe im lokalen Wissensspeicher keine passenden Quellen gefunden."
    lines = [f"Ich habe {result.get('count', len(results))} Treffer im lokalen Wissensspeicher gefunden:"]
    for index, item in enumerate(results[:5], start=1):
        lines.append(f"{index}. {item.get('document_name')} [Chunk {item.get('chunk_index')}]")
        snippet = str(item.get("snippet") or "").strip()
        if snippet:
            lines.append(f"   {snippet}")
    sources = result.get("sources") or []
    if sources:
        lines.append("")
        lines.append("Quellen:")
        for source in sources[:5]:
            lines.append(f"- {source.get('name')}")
    return "\n".join(lines)


def _format_knowledge_documents_answer(result: dict[str, Any]) -> str:
    documents = list(result.get("documents") or [])
    if not documents:
        return "Der lokale Wissensspeicher enthält noch keine Dokumente."
    lines = [f"Ich kenne {result.get('count', len(documents))} Dokumente:"]
    for document in documents[:20]:
        lines.append(f"- {document.get('name')} ({document.get('chunk_count', 0)} Chunks)")
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
    if tool_name.startswith("home_assistant_") and "entities" in tool_name:
        return _format_home_assistant_entity_catalog(tool_name, result)
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



