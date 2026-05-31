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
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant import HomeAssistantTool
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider


app = FastAPI(title="Hammer Jarvis", version="0.1")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1)
    confirm: bool = False


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
