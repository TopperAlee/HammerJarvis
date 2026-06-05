import os
from typing import Any
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent.core import HammerJarvisCore
from app.agent.permissions import classify_action
from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.llm_client import LLMClient, sanitize_identity_response
from app.assistant.missions import MissionController, get_mission_definitions
from app.assistant.priority_engine import PriorityEngine
from app.assistant.system_prompt import SYSTEM_PROMPT
from app.config.personal_priority_rules import (
    add_sender_rule,
    add_subject_rule,
    load_personal_priority_rules,
    remove_rule,
)
from app.config.priority_rules import load_priority_rules
from app.assistant.watchers import WatcherController
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant import HomeAssistantTool
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider


app = FastAPI(title="Hammer Jarvis", version="0.1")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
_watcher_scheduler: Any = None


@app.on_event("startup")
def start_watcher_scheduler() -> None:
    global _watcher_scheduler
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if os.getenv("WATCHER_ENABLED", "false").strip().lower() != "true":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception:
        write_audit_log("watcher_scheduler_unavailable", {})
        return
    interval = int(os.getenv("WATCHER_INTERVAL_SECONDS", "300"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: WatcherController().run_once(), "interval", seconds=interval)
    scheduler.start()
    _watcher_scheduler = scheduler


@app.on_event("shutdown")
def stop_watcher_scheduler() -> None:
    global _watcher_scheduler
    if _watcher_scheduler is not None:
        _watcher_scheduler.shutdown(wait=False)
        _watcher_scheduler = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1)
    confirm: bool = False


class LLMTestRequest(BaseModel):
    message: str = Field(min_length=1)


class MissionRunRequest(BaseModel):
    mission: str = Field(min_length=1)


class EmailScoreRequest(BaseModel):
    sender: str = ""
    subject: str = ""
    snippet: str = ""


class PersonalPriorityRuleRequest(BaseModel):
    match: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    category: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PersonalPriorityRemoveRequest(BaseModel):
    match: str = Field(min_length=1)


class EntityActionRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    confirm: bool = False


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "Hammer Jarvis laeuft",
        "version": "0.1",
        "mode": "local-windows",
    }


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html", media_type="text/html")


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        result = HammerJarvisCore().handle_message(request.message)
        return _attach_chat_answer(result)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.post("/assistant/chat")
def assistant_chat(request: AssistantChatRequest) -> dict[str, Any]:
    try:
        return AssistantOrchestrator().handle_message(
            request.message,
            confirm=request.confirm,
        )
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/assistant/missions")
def assistant_missions() -> dict[str, Any]:
    return get_mission_definitions()


@app.post("/assistant/mission/run")
def assistant_mission_run(request: MissionRunRequest) -> dict[str, Any]:
    try:
        return MissionController().run_mission(request.mission)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/assistant/priority/rules")
def assistant_priority_rules() -> dict[str, Any]:
    return load_priority_rules()


@app.get("/assistant/priority/personal-rules")
def assistant_personal_priority_rules() -> dict[str, Any]:
    return load_personal_priority_rules()


@app.post("/assistant/priority/personal-rules/sender")
def assistant_add_personal_sender_rule(request: PersonalPriorityRuleRequest) -> dict[str, Any]:
    return add_sender_rule(request.match, request.priority, request.category, request.reason)


@app.post("/assistant/priority/personal-rules/subject")
def assistant_add_personal_subject_rule(request: PersonalPriorityRuleRequest) -> dict[str, Any]:
    return add_subject_rule(request.match, request.priority, request.category, request.reason)


@app.delete("/assistant/priority/personal-rules")
def assistant_remove_personal_rule(request: PersonalPriorityRemoveRequest) -> dict[str, Any]:
    return remove_rule(request.match)


@app.post("/assistant/priority/email-score")
def assistant_priority_email_score(request: EmailScoreRequest) -> dict[str, Any]:
    return PriorityEngine().classify_email(request.model_dump())


@app.get("/assistant/watchers/rules")
def assistant_watcher_rules() -> dict[str, Any]:
    return WatcherController().load_rules()


@app.post("/assistant/watchers/run")
def assistant_watchers_run() -> dict[str, Any]:
    return WatcherController().run_once()


@app.get("/assistant/watchers/alerts")
def assistant_watcher_alerts() -> dict[str, Any]:
    return {"alerts": WatcherController().list_alerts()}


@app.post("/assistant/watchers/alerts/{alert_id}/ack")
def assistant_watcher_ack(alert_id: str) -> dict[str, Any]:
    try:
        return WatcherController().acknowledge_alert(alert_id)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.delete("/assistant/watchers/alerts")
def assistant_watcher_clear() -> dict[str, bool]:
    return WatcherController().clear_alerts()


@app.get("/assistant/watchers/status")
def assistant_watcher_status() -> dict[str, Any]:
    return WatcherController().status()


@app.get("/assistant/llm/status")
def assistant_llm_status() -> dict[str, Any]:
    llm = LLMClient()
    return {
        "enabled": llm.is_enabled(),
        "provider": llm.provider_name(),
        "model": llm.model_name(),
        "base_url": llm.base_url(),
        "api_key_configured": bool(llm.api_key),
        "tool_mode": os.getenv("LLM_TOOL_MODE", "true").strip().lower() == "true",
        "available": llm.is_available(),
        "api_key_required": llm.api_key_required(),
    }


@app.post("/assistant/llm/test")
def assistant_llm_test(request: LLMTestRequest) -> dict[str, Any]:
    llm = LLMClient()
    if not llm.is_available():
        return {
            "enabled": llm.is_enabled(),
            "available": False,
            "provider": llm.provider_name(),
            "message": "LLM ist deaktiviert oder die Provider-Konfiguration fehlt.",
        }
    try:
        response = llm.create_response_with_tools(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.message},
            ],
            [],
        )
        return {
            "enabled": True,
            "available": True,
            "provider": llm.provider_name(),
            "answer": sanitize_identity_response(
                request.message,
                response.get("text", ""),
            ),
        }
    except Exception:
        if llm.provider_name() == "ollama":
            return {
                "enabled": True,
                "available": False,
                "provider": "ollama",
                "message": (
                    "Ollama ist nicht erreichbar. Bitte starte Ollama und pruefe "
                    "http://localhost:11434."
                ),
            }
        return {
            "enabled": True,
            "available": False,
            "message": "LLM-Anbindung ist aktuell nicht erreichbar.",
        }


@app.get("/assistant/ollama/status")
def assistant_ollama_status() -> dict[str, Any]:
    llm = LLMClient()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    tags_url = base_url.replace("/v1", "") + "/api/tags"
    model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    try:
        response = requests.get(tags_url, timeout=3)
        response.raise_for_status()
        models = response.json().get("models", [])
        installed = any(item.get("name") == model for item in models)
        return {
            "provider": "ollama",
            "reachable": True,
            "model": model,
            "base_url": base_url,
            "message": (
                "Ollama ist erreichbar und das Modell ist installiert."
                if installed
                else "Ollama ist erreichbar, aber das konfigurierte Modell wurde nicht gefunden."
            ),
        }
    except Exception:
        return {
            "provider": "ollama",
            "reachable": False,
            "model": model,
            "base_url": base_url,
            "message": "Ollama ist nicht erreichbar. Bitte starte Ollama und pruefe http://localhost:11434.",
        }


@app.get("/assistant/providers")
def assistant_providers() -> dict[str, Any]:
    return {
        "email": ["gmail", "outlook_mail"],
        "calendar": ["outlook_calendar", "google_calendar", "timetree"],
        "connected": {
            "gmail": False,
            "outlook_mail": False,
            "outlook_calendar": False,
            "google_calendar": False,
            "timetree": "limited",
        },
    }


@app.get("/assistant/calendar/today")
def assistant_calendar_today() -> dict[str, Any]:
    return CalendarService().list_today_events()


@app.get("/assistant/email/search")
def assistant_email_search(q: str = Query(default="")) -> dict[str, Any]:
    return EmailService().search_emails(q)


@app.get("/assistant/gmail/status")
def assistant_gmail_status() -> dict[str, Any]:
    return GmailProvider().status()


@app.get("/assistant/timetree/status")
def assistant_timetree_status() -> dict[str, Any]:
    return TimeTreeProvider().status()


@app.get("/assistant/timetree/today")
def assistant_timetree_today() -> dict[str, Any]:
    return TimeTreeProvider().list_today_events()


@app.get("/assistant/timetree/events")
def assistant_timetree_events() -> dict[str, Any]:
    return TimeTreeProvider().list_events()


@app.get("/ha/entities")
def get_entities() -> list[dict[str, Any]]:
    try:
        result = HomeAssistantTool().get_all_states()
        write_audit_log("ha_entities", {"count": len(result)})
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/unavailable")
def get_unavailable() -> list[dict[str, Any]]:
    try:
        result = HomeAssistantTool().get_unavailable_entities()
        write_audit_log("ha_unavailable", {"count": len(result)})
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/problems")
def get_problems() -> dict[str, Any]:
    try:
        result = HomeAssistantTool().get_problem_entities()
        write_audit_log(
            "ha_problems",
            {
                "critical_count": result["critical_count"],
                "warning_count": result["warning_count"],
                "informational_count": result["informational_count"],
            },
        )
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/ecoflow")
def get_ecoflow() -> dict[str, Any]:
    try:
        result = HomeAssistantTool().diagnose_ecoflow()
        write_audit_log(
            "ha_ecoflow",
            {
                "total": result["total"],
                "unavailable_count": result["unavailable_count"],
                "unknown_count": result["unknown_count"],
            },
        )
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/ecoflow/energy")
def get_ecoflow_energy() -> dict[str, Any]:
    try:
        result = HomeAssistantTool().get_ecoflow_energy_overview()
        write_audit_log(
            "ha_ecoflow_energy",
            {
                "has_pv_power": result["pv_power_w"] is not None,
                "has_soc": result["soc_percent"] is not None,
            },
        )
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/search")
def search_entities(q: str = Query(min_length=1)) -> list[dict[str, Any]]:
    try:
        result = HomeAssistantTool().search_entities(q)
        write_audit_log("ha_search", {"query": q, "count": len(result)})
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/power")
def get_power() -> list[dict[str, Any]]:
    try:
        result = HomeAssistantTool().get_power_entities()
        write_audit_log("ha_power", {"count": len(result)})
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/ha/entity/{entity_id}")
def get_entity(entity_id: str) -> dict[str, Any]:
    try:
        result = HomeAssistantTool().get_entity_state(entity_id)
        write_audit_log("ha_entity", {"entity_id": entity_id})
        return result
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.post("/ha/turn-on")
def turn_on(request: EntityActionRequest) -> dict[str, Any]:
    return _run_confirmed_action("turn_on", request.entity_id, request.confirm)


@app.post("/ha/turn-off")
def turn_off(request: EntityActionRequest) -> dict[str, Any]:
    return _run_confirmed_action("turn_off", request.entity_id, request.confirm)


def _run_confirmed_action(action: str, entity_id: str, confirm: bool) -> dict[str, Any]:
    risk = classify_action(action)
    if not confirm:
        write_audit_log(
            "confirmation_required",
            {"action": action, "entity_id": entity_id, "risk": risk},
        )
        return {
            "confirmation_required": True,
            "action": action,
            "entity_id": entity_id,
            "risk": risk,
        }

    try:
        tool = HomeAssistantTool()
        result = tool.turn_on(entity_id) if action == "turn_on" else tool.turn_off(entity_id)
        write_audit_log(
            action,
            {"entity_id": entity_id, "risk": risk, "outcome": "executed"},
        )
        return {
            "confirmation_required": False,
            "action": action,
            "entity_id": entity_id,
            "risk": risk,
            "result": result,
        }
    except Exception as exc:
        write_audit_log(
            action,
            {"entity_id": entity_id, "risk": risk, "outcome": "failed"},
        )
        raise _to_http_exception(exc) from exc


def _attach_chat_answer(result: dict[str, Any]) -> dict[str, Any]:
    if "answer" in result:
        return result
    answer = result.get("message")
    human_status = result.get("human_status")
    overview = result.get("overview")
    problems = result.get("problems")
    entities = result.get("entities")
    if not answer and isinstance(human_status, dict):
        answer = _format_human_status_answer(human_status)
    if not answer and isinstance(overview, dict) and isinstance(
        overview.get("human_status"), dict
    ):
        answer = _format_human_status_answer(overview["human_status"])
    if not answer and isinstance(problems, dict):
        answer = (
            "Home Assistant Diagnose: "
            f"{problems.get('critical_count', 0)} kritisch, "
            f"{problems.get('warning_count', 0)} Warnungen, "
            f"{problems.get('informational_count', 0)} Hinweise."
        )
    if not answer and isinstance(entities, list):
        answer = f"Ich habe {len(entities)} passende Entities gefunden."
    return {**result, "answer": answer or "Ich habe eine Antwort erhalten."}


def _format_human_status_answer(human_status: dict[str, Any]) -> str:
    details = human_status.get("details", [])
    headline = str(human_status.get("headline", ""))
    if details:
        return f"{headline} {'; '.join(str(item) for item in details)}"
    return headline


def _to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else 502
        if status_code == 404:
            return HTTPException(status_code=404, detail="Entity not found")
        return HTTPException(status_code=502, detail="Home Assistant API error")
    if isinstance(exc, requests.exceptions.RequestException):
        return HTTPException(status_code=502, detail="Home Assistant connection error")
    return HTTPException(status_code=500, detail="Internal server error")
