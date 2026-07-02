import os
import re
import time
import threading
from dataclasses import asdict
from uuid import uuid4
from typing import Any
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import File, FastAPI, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent.core import HammerJarvisCore
from app.agent.permissions import classify_action
from app.assistant.actions.action_executor import ActionExecutor
from app.assistant.actions.pending_action_store import pending_action_store
from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.llm_client import LLMClient, sanitize_identity_response
from app.assistant.llm.native_ollama_client import NativeOllamaClient
from app.assistant.knowledge.knowledge_store import KnowledgeStore
from app.assistant.knowledge.storage import SUPPORTED_KNOWLEDGE_EXTENSIONS, max_upload_bytes
from app.assistant.memory.memory_classifier import MemoryClassifier
from app.assistant.memory.memory_store import MemoryStore
from app.assistant.performance.metrics_store import metrics_store
from app.assistant.missions import MissionController, get_mission_definitions
from app.assistant.priority_engine import PriorityEngine
from app.assistant.skills.skill_registry import SkillRegistry
from app.assistant.system_prompt import SYSTEM_PROMPT
from app.assistant.voice.wake_word_events import error_event, ready_event, status_event
from app.assistant.voice.wake_word_service import wake_word_service
from app.desktop_agent.event_bridge import desktop_event_bridge
from app.assistant.session_state import open_best_match, open_result_by_index, session_state
from app.assistant.tool_registry import ToolRegistry
from app.config.personal_priority_rules import (
    add_sender_rule,
    add_subject_rule,
    load_personal_priority_rules,
    remove_rule,
)
from app.config.priority_rules import load_priority_rules
from app.assistant.watchers import WatcherController
from app.tools.files.content_search_tool import ContentSearchTool
from app.tools.files.file_creator import FileCreatorTool
from app.tools.files.file_inspect_tool import FileInspectTool
from app.tools.files.file_open_tool import FileOpenTool
from app.tools.files.file_search_tool import FileSearchTool, get_file_search_status
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant import HomeAssistantTool
from app.tools.home_assistant_actions import HomeAssistantActionTool
from app.tools.home_assistant_control_broker import HomeAssistantControlBroker
from app.tools.home_assistant_entities import HomeAssistantEntityCatalog
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider
from app.tools.web.web_research_tool import WebResearchTool, get_web_research_status
from hammer_jarvis.engineering.demo import get_demo_projects
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphBuilder, GraphNode
from hammer_jarvis.engineering.importer.project_importer import ImportedProject, ProjectImporter
from hammer_jarvis.engineering.plugins import get_engineering_modules
from hammer_jarvis.engineering.scanner.filesystem import ProjectScanner
from hammer_jarvis.engineering.tree import EngineeringTreeBuilder
from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.intent.models import IntentRequest
from hammer_jarvis.intent.parser import IntentParser
from hammer_jarvis.intent.recommendations import RecommendationEngine
from hammer_jarvis.intent.registry import get_commands
from hammer_jarvis.tools.protool.report import analyze_protool_csv


app = FastAPI(title="Hammer Jarvis", version="0.1")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
_watcher_scheduler: Any = None
_ha_entity_scheduler: Any = None
_last_native_benchmark: dict[str, Any] | None = None
_last_native_warm_benchmark: dict[str, Any] | None = None
_engineering_project_store: dict[str, ImportedProject] = {}
_intent_context_store = ContextStore()


@app.on_event("startup")
def start_ollama_warmup() -> None:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if os.getenv("OLLAMA_WARMUP_ENABLED", "false").strip().lower() != "true":
        return
    if os.getenv("OLLAMA_WARMUP_ON_STARTUP", "false").strip().lower() != "true":
        return

    def warmup() -> None:
        try:
            llm = LLMClient()
            if llm.provider_name() != "ollama" or not llm.is_available():
                return
            native = NativeOllamaClient()
            model = llm.fast_model_name() if native.is_model_installed(llm.fast_model_name()) else llm.model_name()
            response = native.benchmark_model(model)
            write_audit_log("ollama_warmup", {"duration_ms": response.get("duration_ms"), "model": model})
        except Exception:
            write_audit_log("ollama_warmup_failed", {})

    threading.Thread(target=warmup, daemon=True).start()


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


@app.on_event("startup")
def start_ha_entity_scheduler() -> None:
    global _ha_entity_scheduler
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if os.getenv("HA_ENTITY_SYNC_ENABLED", "true").strip().lower() != "true":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception:
        write_audit_log("ha_entity_sync_scheduler_unavailable", {})
        return
    interval = int(os.getenv("HA_ENTITY_SYNC_INTERVAL_SECONDS", "300"))

    def sync_job() -> None:
        try:
            result = HomeAssistantEntityCatalog().sync_entities(force=True)
            write_audit_log("ha_entity_sync", {"entity_count": result.get("entity_count", 0), "source": result.get("source")})
        except Exception:
            write_audit_log("ha_entity_sync_failed", {})

    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_job, "interval", seconds=interval)
    scheduler.start()
    _ha_entity_scheduler = scheduler


@app.on_event("shutdown")
def stop_watcher_scheduler() -> None:
    global _watcher_scheduler, _ha_entity_scheduler
    if _watcher_scheduler is not None:
        _watcher_scheduler.shutdown(wait=False)
        _watcher_scheduler = None
    if _ha_entity_scheduler is not None:
        _ha_entity_scheduler.shutdown(wait=False)
        _ha_entity_scheduler = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1)
    confirm: bool = False


class ActionExecuteRequest(BaseModel):
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


class MemoryCreateRequest(BaseModel):
    type: str = "fact"
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    tags: list[str] = []
    source: str = "user"
    confidence: str = "high"
    protected: bool = False


class MemoryPatchRequest(BaseModel):
    type: str | None = None
    key: str | None = None
    value: str | None = None
    tags: list[str] | None = None
    confidence: str | None = None
    protected: bool | None = None


class MemoryRepairRequest(BaseModel):
    dry_run: bool = True


class KnowledgeIndexRequest(BaseModel):
    path: str = Field(min_length=1)
    recursive: bool = True


class EngineeringOpenProjectRequest(BaseModel):
    path: str = Field(min_length=1)


class ContextUpdateRequest(BaseModel):
    active_workspace: str | None = None
    active_project_id: str | None = None
    active_project_name: str | None = None
    active_project_path: str | None = None
    active_file: str | None = None
    active_file_type: str | None = None
    active_panel: str | None = None
    active_language: str | None = None
    last_intent: str | None = None
    last_search_query: str | None = None
    last_selected_node: str | None = None
    current_task: str | None = None


class ProToolAnalyzeRequest(BaseModel):
    file_path: str = Field(min_length=1)
    panel: str = Field(min_length=1)
    text_column: int = Field(ge=1)
    encoding: str = "cp1252"
    report_empty: bool = False
    include_preview: bool = False


class ProToolAnalyzeBatchRequest(BaseModel):
    file_paths: list[str] = Field(min_length=1)
    panel: str = Field(min_length=1)
    text_column: int = Field(ge=1)
    encoding: str = "cp1252"
    report_empty: bool = False
    include_preview: bool = False


KNOWLEDGE_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
KNOWLEDGE_DETAIL_PREVIEW_COUNT = 5
KNOWLEDGE_DETAIL_PREVIEW_CHARS = 320
PROTOOL_UPLOAD_DIR = Path("workspace") / "exports" / "protool_uploads"
PROTOOL_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _safe_protool_upload_name(filename: str | None) -> str:
    original_name = Path(filename or "protool.csv").name
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", original_name).strip(" .")
    return sanitized or "protool.csv"


async def _save_protool_upload(upload: UploadFile) -> tuple[Path, str]:
    original_name = _safe_protool_upload_name(upload.filename)
    PROTOOL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = PROTOOL_UPLOAD_DIR / f"{uuid4().hex}_{original_name}"
    with target.open("wb") as handle:
        while True:
            chunk = await upload.read(PROTOOL_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            handle.write(chunk)
    return target, original_name


def _engineering_demo_graph(project_id: str = "demo-project") -> EngineeringGraph:
    try:
        return GraphBuilder().build_demo_graph(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _graph_payload(graph: EngineeringGraph) -> dict[str, Any]:
    return {
        "nodes": [asdict(node) for node in graph.nodes],
        "edges": [asdict(edge) for edge in graph.edges],
    }


def _node_payload(node: GraphNode | None) -> dict[str, Any]:
    if node is None:
        raise HTTPException(status_code=404, detail="Engineering graph node not found.")
    return asdict(node)


def _imported_project_payload(imported: ImportedProject) -> dict[str, Any]:
    return {
        "project": asdict(imported.project),
        "graph": _graph_payload(imported.graph),
    }


def _get_imported_project(project_id: str) -> ImportedProject:
    imported = _engineering_project_store.get(project_id)
    if imported is None:
        raise HTTPException(status_code=404, detail="Engineering project not found.")
    return imported


class EntityActionRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    confirm: bool = False


class HomeAssistantAllowlistAddRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    friendly_name: str = ""
    domain: str = Field(min_length=1)
    allowed_actions: list[str] = []
    confirm: bool = False


class HomeAssistantAllowlistRemoveRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    confirm: bool = False


class HomeAssistantEntitySyncRequest(BaseModel):
    force: bool = False


class HomeAssistantControlResolveRequest(BaseModel):
    command: str = Field(min_length=1)


class HomeAssistantControlPrepareRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    parameters: dict[str, Any] | None = None


class HomeAssistantControlExecuteRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    parameters: dict[str, Any] | None = None
    confirm: bool = False


class HomeAssistantBatchPrepareRequest(BaseModel):
    domain: str = Field(min_length=1)
    action: str = Field(min_length=1)


class HomeAssistantBatchExecuteRequest(BaseModel):
    actions: list[dict[str, Any]]
    confirm: bool = False


class ExcelCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    sheets: list[dict[str, Any]]
    filename: str | None = None


class CsvCreateRequest(BaseModel):
    headers: list[str]
    rows: list[list[Any]] = []
    filename: str | None = None


class MarkdownCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = ""
    filename: str | None = None


class JsonCreateRequest(BaseModel):
    data: dict[str, Any]
    filename: str | None = None


class FileOpenRequest(BaseModel):
    path: str = Field(min_length=1)


class FileInspectRequest(BaseModel):
    path: str = Field(min_length=1)
    query: str | None = None


class FileSummarizeRequest(BaseModel):
    path: str = Field(min_length=1)
    focus: str | None = None


class FileExtractKeyFieldsRequest(BaseModel):
    path: str = Field(min_length=1)
    document_type: str | None = None


class FileOpenResultRequest(BaseModel):
    index: int = Field(ge=1)


class WebResearchRequest(BaseModel):
    query: str = Field(min_length=1)


class SkillDocumentSummarizeRequest(BaseModel):
    path: str = Field(min_length=1)
    focus: str | None = None


class SkillDocumentKeyFieldsRequest(BaseModel):
    path: str = Field(min_length=1)
    document_type: str | None = None


class SkillFileSearchReportRequest(BaseModel):
    query: str = Field(min_length=1)
    extensions: list[str] | None = None
    content_search: bool = False


class SkillDocumentIndexExcelRequest(BaseModel):
    query: str = Field(min_length=1)
    extensions: list[str] | None = None


class SkillWebResearchRequest(BaseModel):
    query: str = Field(min_length=1)


class DesktopWakeRequest(BaseModel):
    type: str = "wake_detected"
    wake_word: str = "Jarvis"
    source: str = "desktop_agent"
    engine: str | None = None
    culture: str | None = None
    confidence: float | None = None
    timestamp: str | None = None


class DesktopHeartbeatRequest(BaseModel):
    state: str = "READY"
    agent_state: str | None = None
    description: str | None = None
    backend_ready: bool | None = None
    event_bridge_ready: bool | None = None
    wake_listener_ready: bool | None = None
    wake_listener_alive: bool | None = None
    wake_listener_pid: int | None = None
    wake_audio_ready: bool | None = None
    wake_audio_state: str | None = None
    wake_last_audio_level: int | None = None
    wake_last_audio_at: str | None = None
    wake_last_speech_detected_at: str | None = None
    wake_last_rejected_confidence: float | None = None
    wake_engine: str | None = None
    wake_word: str | None = None
    wake_culture: str | None = None
    wake_recognizer: str | None = None
    wake_threshold: float | None = None
    wake_ready_at: str | None = None
    last_wake_detection_at: str | None = None
    last_error: str | None = None
    ready_announcement_enabled: bool | None = None
    ready_announcement_attempted: bool | None = None
    ready_announcement_succeeded: bool | None = None
    ready_announcement_error: str | None = None
    agent_python: str | None = None
    backend_python: str | None = None
    project_root: str | None = None
    websocket_transport: str | None = None
    backend_pid: int | None = None


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "Hammer Jarvis laeuft",
        "version": "0.1",
        "mode": "local-windows",
    }


@app.get("/assistant/health")
def assistant_health() -> dict[str, str]:
    return {
        "status": "ready",
        "version": "0.1",
        "mode": "local-windows",
    }


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html", media_type="text/html")


@app.get("/assistant/voice/wake/status")
def assistant_voice_wake_status() -> dict[str, Any]:
    return wake_word_service.status()


@app.get("/assistant/desktop/status")
def assistant_desktop_status() -> dict[str, Any]:
    return desktop_event_bridge.status()


@app.post("/assistant/desktop/agent-heartbeat")
def assistant_desktop_agent_heartbeat(request: DesktopHeartbeatRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude_none=True)
    if "agent_state" not in payload:
        payload["agent_state"] = payload.pop("state", "READY")
    return desktop_event_bridge.heartbeat(payload)


@app.post("/assistant/desktop/wake")
async def assistant_desktop_wake(request: DesktopWakeRequest) -> dict[str, Any]:
    return await desktop_event_bridge.broadcast_wake(request.model_dump())


@app.websocket("/assistant/desktop/events")
async def assistant_desktop_events(websocket: WebSocket) -> None:
    origin = (websocket.headers.get("origin") or "").rstrip("/")
    host = websocket.headers.get("host") or ""
    if not _desktop_event_origin_allowed(origin, host):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await desktop_event_bridge.connect_dashboard(websocket)
    try:
        await websocket.send_json({"type": "desktop_status", **desktop_event_bridge.status()})
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "heartbeat":
                await websocket.send_json({"type": "desktop_status", **desktop_event_bridge.dashboard_heartbeat()})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await desktop_event_bridge.disconnect_dashboard(websocket)


def _desktop_event_origin_allowed(origin: str, host: str) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    origin_host = parsed.netloc.lower()
    request_host = (host or "").lower()
    if origin_host == request_host:
        return True
    local_hosts = {"127.0.0.1", "localhost"}
    origin_name, _, origin_port = origin_host.partition(":")
    request_name, _, request_port = request_host.partition(":")
    return origin_name in local_hosts and request_name in local_hosts and origin_port == request_port


@app.websocket("/assistant/voice/wake/stream")
async def assistant_voice_wake_stream(websocket: WebSocket) -> None:
    if not wake_word_service.origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return

    if not await wake_word_service.connect_client():
        await websocket.accept()
        await websocket.send_json(error_event("max_clients", "Es ist bereits ein Wake-Word-Client verbunden."))
        await websocket.close(code=1013)
        return

    config = wake_word_service.config
    await websocket.accept()
    try:
        await websocket.send_json(ready_event(config.model, config.sample_rate, config.frame_ms))
        await websocket.send_json(status_event("listening"))
        while True:
            message = await websocket.receive()
            frame = message.get("bytes")
            if frame is not None:
                await websocket.send_json(await wake_word_service.process_frame(frame))
                continue
            if message.get("text") is not None:
                await websocket.send_json(error_event("invalid_message", "Nur binaere PCM-Frames werden akzeptiert."))
    except WebSocketDisconnect:
        pass
    finally:
        await wake_word_service.disconnect_client()


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


@app.get("/assistant/actions/pending")
def assistant_actions_pending() -> dict[str, Any]:
    actions = pending_action_store.present_actions(pending_action_store.list_pending_actions(), source="dashboard")
    return {"count": len(actions), "actions": actions}


@app.get("/assistant/home-assistant/actions/allowed")
def assistant_home_assistant_allowed_actions() -> dict[str, Any]:
    return HomeAssistantActionTool().list_allowed_actions()


@app.get("/assistant/home-assistant/actions/candidates")
def assistant_home_assistant_action_candidates() -> dict[str, Any]:
    return HomeAssistantActionTool().discover_actionable_entities()


@app.get("/assistant/home-assistant/actions/allowlist")
def assistant_home_assistant_action_allowlist() -> dict[str, Any]:
    return HomeAssistantActionTool().list_allowed_actions()


@app.post("/assistant/home-assistant/actions/allowlist/add")
def assistant_home_assistant_action_allowlist_add(request: HomeAssistantAllowlistAddRequest) -> dict[str, Any]:
    arguments = {
        "entity_id": request.entity_id,
        "friendly_name": request.friendly_name or request.entity_id,
        "domain": request.domain,
        "allowed_actions": request.allowed_actions,
    }
    if request.confirm:
        return ToolRegistry().execute_tool("home_assistant_add_to_allowlist", arguments, confirm=True)
    action = pending_action_store.create_action(
        {
            "title": f"{request.friendly_name or request.entity_id} zur Smart-Home-Freigabe hinzufügen",
            "description": "Änderung an der Smart-Home-Freigabe. Ausführung erst nach Bestätigung.",
            "tool_name": "home_assistant_add_to_allowlist",
            "arguments": arguments,
            "risk": "YELLOW",
            "source": "home_assistant_allowlist_api",
            "requires_confirmation": True,
        }
    )
    return {"pending": True, "action": action, "message": "Freigabeänderung wurde als gelbe Aktion vorbereitet."}


@app.post("/assistant/home-assistant/actions/allowlist/remove")
def assistant_home_assistant_action_allowlist_remove(request: HomeAssistantAllowlistRemoveRequest) -> dict[str, Any]:
    arguments = {"entity_id": request.entity_id}
    if request.confirm:
        return ToolRegistry().execute_tool("home_assistant_remove_from_allowlist", arguments, confirm=True)
    action = pending_action_store.create_action(
        {
            "title": f"{request.entity_id} aus Smart-Home-Freigabe entfernen",
            "description": "Änderung an der Smart-Home-Freigabe. Ausführung erst nach Bestätigung.",
            "tool_name": "home_assistant_remove_from_allowlist",
            "arguments": arguments,
            "risk": "YELLOW",
            "source": "home_assistant_allowlist_api",
            "requires_confirmation": True,
        }
    )
    return {"pending": True, "action": action, "message": "Freigabeänderung wurde als gelbe Aktion vorbereitet."}


@app.get("/assistant/home-assistant/entities/status")
def assistant_home_assistant_entities_status() -> dict[str, Any]:
    return HomeAssistantEntityCatalog().status()


@app.post("/assistant/home-assistant/entities/sync")
def assistant_home_assistant_entities_sync(request: HomeAssistantEntitySyncRequest | None = None) -> dict[str, Any]:
    force = bool(request.force) if request else False
    return HomeAssistantEntityCatalog().sync_entities(force=force)


@app.get("/assistant/home-assistant/entities")
def assistant_home_assistant_entities(
    domain: str | None = None,
    state: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    return HomeAssistantEntityCatalog().list_entities(domain=domain, state=state, limit=limit)


@app.get("/assistant/home-assistant/entities/search")
def assistant_home_assistant_entities_search(
    q: str = Query(..., min_length=1),
    domain: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    return HomeAssistantEntityCatalog().search_entities(query=q, domain=domain, limit=limit)


@app.get("/assistant/home-assistant/entities/unavailable")
def assistant_home_assistant_entities_unavailable(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return HomeAssistantEntityCatalog().list_unavailable_entities(limit=limit)


@app.get("/assistant/home-assistant/entities/actionable-candidates")
def assistant_home_assistant_entities_actionable_candidates(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return HomeAssistantEntityCatalog().list_actionable_candidates(limit=limit)


@app.get("/assistant/home-assistant/entities/{entity_id}")
def assistant_home_assistant_entity(entity_id: str) -> dict[str, Any]:
    return HomeAssistantEntityCatalog().get_entity(entity_id)


@app.get("/assistant/home-assistant/control/policy")
def assistant_home_assistant_control_policy() -> dict[str, Any]:
    return HomeAssistantControlBroker().list_control_policy()


@app.get("/assistant/home-assistant/control/auto-policy")
def assistant_home_assistant_control_auto_policy() -> dict[str, Any]:
    return HomeAssistantControlBroker().list_auto_policy()


@app.post("/assistant/home-assistant/control/auto-policy/reload")
def assistant_home_assistant_control_auto_policy_reload() -> dict[str, Any]:
    policy = HomeAssistantControlBroker().list_auto_policy()
    return {"reloaded": True, **policy}


@app.get("/assistant/home-assistant/control/trusted-switches")
def assistant_home_assistant_control_trusted_switches() -> dict[str, Any]:
    return HomeAssistantControlBroker().list_trusted_switches()


@app.get("/assistant/home-assistant/control/entities")
def assistant_home_assistant_control_entities(domain: str | None = None) -> dict[str, Any]:
    return HomeAssistantControlBroker().list_controllable_entities(domain=domain)


@app.post("/assistant/home-assistant/control/resolve")
def assistant_home_assistant_control_resolve(request: HomeAssistantControlResolveRequest) -> dict[str, Any]:
    return HomeAssistantControlBroker().resolve_control_intent(request.command)


@app.post("/assistant/home-assistant/control/prepare")
def assistant_home_assistant_control_prepare(request: HomeAssistantControlPrepareRequest) -> dict[str, Any]:
    return HomeAssistantControlBroker().prepare_control_action(
        request.entity_id,
        request.action,
        request.parameters or {},
    )


@app.post("/assistant/home-assistant/control/execute")
def assistant_home_assistant_control_execute(request: HomeAssistantControlExecuteRequest) -> dict[str, Any]:
    if not request.confirm:
        return {"confirmation_required": True, "message": "Diese Home-Assistant-Aktion benötigt Bestätigung."}
    return HomeAssistantControlBroker().execute_control_action(request.entity_id, request.action, request.parameters or {})


@app.post("/assistant/home-assistant/control/batch/prepare")
def assistant_home_assistant_control_batch_prepare(request: HomeAssistantBatchPrepareRequest) -> dict[str, Any]:
    return HomeAssistantControlBroker().prepare_batch_action(request.domain, request.action)


@app.post("/assistant/home-assistant/control/batch/execute")
def assistant_home_assistant_control_batch_execute(request: HomeAssistantBatchExecuteRequest) -> dict[str, Any]:
    if not request.confirm:
        return {"confirmation_required": True, "message": "Diese Home-Assistant-Batch-Aktion benötigt Bestätigung."}
    return HomeAssistantControlBroker().execute_batch_action(request.actions)


@app.post("/assistant/actions/{action_id}/execute")
def assistant_action_execute(action_id: str, request: ActionExecuteRequest) -> dict[str, Any]:
    return ActionExecutor().execute(action_id, confirm=request.confirm)


@app.post("/assistant/actions/{action_id}/reject")
def assistant_action_reject(action_id: str) -> dict[str, Any]:
    return pending_action_store.reject_action(action_id)


@app.delete("/assistant/actions/expired")
def assistant_actions_expire() -> dict[str, Any]:
    expired = pending_action_store.expire_old_actions()
    return {"expired_count": len(expired), "expired": expired}


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


@app.post("/assistant/files/create/excel")
def assistant_create_excel(request: ExcelCreateRequest) -> dict[str, Any]:
    try:
        return FileCreatorTool().create_excel_file(request.title, request.sheets, request.filename)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.post("/assistant/files/create/csv")
def assistant_create_csv(request: CsvCreateRequest) -> dict[str, Any]:
    try:
        return FileCreatorTool().create_csv_file(request.headers, request.rows, request.filename)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.post("/assistant/files/create/markdown")
def assistant_create_markdown(request: MarkdownCreateRequest) -> dict[str, Any]:
    try:
        return FileCreatorTool().create_markdown_file(request.title, request.content, request.filename)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.post("/assistant/files/create/json")
def assistant_create_json(request: JsonCreateRequest) -> dict[str, Any]:
    try:
        return FileCreatorTool().create_json_file(request.data, request.filename)
    except Exception as exc:
        raise _to_http_exception(exc) from exc


@app.get("/assistant/files/exports")
def assistant_file_exports() -> dict[str, Any]:
    return FileCreatorTool().list_exports()


@app.get("/assistant/files/search")
def assistant_file_search(q: str = Query(min_length=1), extension: str | None = None) -> dict[str, Any]:
    extensions = [extension] if extension else None
    return FileSearchTool().search_files(q, extensions=extensions)


@app.get("/assistant/files/content-search")
def assistant_file_content_search(q: str = Query(min_length=1), extension: str | None = None) -> dict[str, Any]:
    extensions = [extension] if extension else None
    return ContentSearchTool().search_file_contents(q, extensions=extensions)


@app.post("/assistant/files/inspect")
def assistant_file_inspect(request: FileInspectRequest) -> dict[str, Any]:
    return FileInspectTool().inspect_file(request.path, request.query)


@app.post("/assistant/files/summarize")
def assistant_file_summarize(request: FileSummarizeRequest) -> dict[str, Any]:
    return FileInspectTool().summarize_file(request.path, request.focus)


@app.post("/assistant/files/extract-key-fields")
def assistant_file_extract_key_fields(request: FileExtractKeyFieldsRequest) -> dict[str, Any]:
    return FileInspectTool().extract_key_fields(request.path, request.document_type)


@app.post("/assistant/files/open-best-match")
def assistant_file_open_best_match() -> dict[str, Any]:
    return open_best_match()


@app.post("/assistant/files/open-result")
def assistant_file_open_result(request: FileOpenResultRequest) -> dict[str, Any]:
    return open_result_by_index(request.index)


@app.get("/assistant/files/last-results")
def assistant_file_last_results() -> dict[str, Any]:
    return session_state.get_last_file_results()


@app.get("/assistant/files/recent")
def assistant_file_recent(limit: int = 10) -> dict[str, Any]:
    return FileSearchTool().list_recent_exports(limit=limit)


@app.get("/assistant/files/status")
def assistant_file_status() -> dict[str, Any]:
    return get_file_search_status()


@app.post("/assistant/files/open")
def assistant_file_open(request: FileOpenRequest) -> dict[str, Any]:
    return FileOpenTool().open_file(request.path)


@app.post("/assistant/files/open-latest")
def assistant_file_open_latest() -> dict[str, Any]:
    return FileOpenTool().open_latest_export()


@app.post("/assistant/intent/parse")
def assistant_intent_parse(request: IntentRequest) -> dict[str, Any]:
    current_context = _intent_context_store.get().model_dump()
    merged_context = {**current_context, **request.context}
    result = IntentParser().parse_text(request.text, source=request.source, context=merged_context)
    _intent_context_store.update({"last_intent": result.intent})
    if result.intent == "knowledge.search":
        _intent_context_store.update({"last_search_query": request.text})
    return result.model_dump()


@app.get("/assistant/context")
def assistant_context() -> dict[str, Any]:
    return _intent_context_store.get().model_dump()


@app.post("/assistant/context/update")
def assistant_context_update(request: ContextUpdateRequest) -> dict[str, Any]:
    patch = request.model_dump(exclude_unset=True)
    return _intent_context_store.update(patch).model_dump()


@app.post("/assistant/context/reset")
def assistant_context_reset() -> dict[str, Any]:
    return _intent_context_store.reset().model_dump()


@app.get("/assistant/recommendations")
def assistant_recommendations() -> list[dict[str, Any]]:
    context = _intent_context_store.get()
    knowledge_empty = _is_knowledge_empty()
    recommendations = RecommendationEngine(knowledge_empty=knowledge_empty, voice_ready=False).build(context)
    return [recommendation.model_dump() for recommendation in recommendations]


def _is_knowledge_empty() -> bool:
    try:
        return int(KnowledgeStore().status().get("document_count", 0)) == 0
    except Exception:
        return False


@app.get("/assistant/commands")
def assistant_commands() -> list[dict[str, object]]:
    return get_commands()


@app.get("/assistant/capabilities")
def assistant_capabilities() -> list[dict[str, Any]]:
    return [capability.model_dump() for capability in CapabilityRegistry().list()]


@app.get("/assistant/engineering/modules")
def assistant_engineering_modules() -> list[dict[str, str]]:
    return get_engineering_modules()


@app.get("/assistant/engineering/projects")
def assistant_engineering_projects() -> list[dict[str, Any]]:
    imported_projects = [asdict(imported.project) for imported in _engineering_project_store.values()]
    return get_demo_projects() + imported_projects


@app.post("/assistant/engineering/projects/open")
def assistant_engineering_open_project(request: EngineeringOpenProjectRequest) -> dict[str, Any]:
    try:
        scan_result = ProjectScanner().scan(request.path)
        imported = ProjectImporter().import_scan(scan_result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _engineering_project_store[imported.project.id] = imported
    _intent_context_store.update(
        {
            "active_workspace": "engineering",
            "active_project_id": imported.project.id,
            "active_project_name": imported.project.name,
            "active_project_path": request.path,
        }
    )
    return {
        "project_id": imported.project.id,
        "project_name": imported.project.name,
        "file_count": len(imported.project.files),
    }


@app.get("/assistant/engineering/projects/{project_id}")
def assistant_engineering_project(project_id: str) -> dict[str, Any]:
    return _imported_project_payload(_get_imported_project(project_id))


@app.get("/assistant/engineering/projects/{project_id}/tree")
def assistant_engineering_project_tree(project_id: str) -> dict[str, Any]:
    imported = _get_imported_project(project_id)
    return EngineeringTreeBuilder().build(imported.project)


@app.get("/assistant/engineering/projects/{project_id}/files")
def assistant_engineering_project_files(project_id: str) -> dict[str, Any]:
    imported = _get_imported_project(project_id)
    return {"project_id": project_id, "files": [asdict(project_file) for project_file in imported.project.files]}


@app.get("/assistant/engineering/graph/projects/{project_id}")
def assistant_engineering_graph_project(project_id: str) -> dict[str, Any]:
    return _graph_payload(_engineering_demo_graph(project_id))


@app.get("/assistant/engineering/graph/nodes/{node_id}")
def assistant_engineering_graph_node(node_id: str) -> dict[str, Any]:
    graph = _engineering_demo_graph()
    return _node_payload(graph.get_node(node_id))


@app.get("/assistant/engineering/graph/search")
def assistant_engineering_graph_search(q: str = Query(min_length=1)) -> dict[str, Any]:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query must not be empty.")
    graph = _engineering_demo_graph()
    return {"query": q, "results": [asdict(node) for node in graph.search(q)]}


@app.get("/assistant/engineering/graph/impact/{node_id}")
def assistant_engineering_graph_impact(node_id: str) -> dict[str, Any]:
    graph = _engineering_demo_graph()
    if graph.get_node(node_id) is None:
        raise HTTPException(status_code=404, detail="Engineering graph node not found.")
    return {"node_id": node_id, "nodes": [asdict(node) for node in graph.impact(node_id)]}


@app.post("/assistant/protool/analyze")
def assistant_protool_analyze(request: ProToolAnalyzeRequest) -> dict[str, Any]:
    try:
        return analyze_protool_csv(
            request.file_path,
            panel=request.panel,
            text_column=request.text_column,
            encoding=request.encoding,
            report_empty_texts=request.report_empty,
            include_preview=request.include_preview,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/assistant/protool/upload-analyze")
async def assistant_protool_upload_analyze(
    file: UploadFile = File(...),
    panel: str = Form(...),
    text_column: int = Form(...),
    encoding: str = Form("cp1252"),
    include_preview: bool = Form(False),
) -> dict[str, Any]:
    temp_path: Path | None = None
    try:
        temp_path, _original_name = await _save_protool_upload(file)
        return analyze_protool_csv(
            temp_path,
            panel=panel,
            text_column=text_column,
            encoding=encoding,
            include_preview=include_preview,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


@app.post("/assistant/protool/analyze-batch")
def assistant_protool_analyze_batch(request: ProToolAnalyzeBatchRequest) -> dict[str, Any]:
    try:
        reports = [
            analyze_protool_csv(
                file_path,
                panel=request.panel,
                text_column=request.text_column,
                encoding=request.encoding,
                report_empty_texts=request.report_empty,
                include_preview=request.include_preview,
            )
            for file_path in request.file_paths
        ]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "files": reports,
        "summary": {
            "file_count": len(reports),
            "total_rows": sum(int(report.get("rows") or 0) for report in reports),
            "total_checked_rows": sum(int(report.get("checked_rows") or 0) for report in reports),
            "total_issues": sum(len(report.get("issues") or []) for report in reports),
        },
    }


@app.get("/assistant/web/status")
def assistant_web_status() -> dict[str, Any]:
    return get_web_research_status()


@app.get("/assistant/web/search")
def assistant_web_search(q: str = Query(min_length=1)) -> dict[str, Any]:
    return WebResearchTool().search_web(q)


@app.post("/assistant/web/research")
def assistant_web_research(request: WebResearchRequest) -> dict[str, Any]:
    return WebResearchTool().research(request.query)


@app.get("/assistant/skills")
def assistant_skills() -> dict[str, Any]:
    return SkillRegistry().list_skills()


@app.post("/assistant/skills/document/summarize")
def assistant_skill_document_summarize(request: SkillDocumentSummarizeRequest) -> dict[str, Any]:
    return SkillRegistry().execute(
        "document_summarize",
        {"path": request.path, "focus": request.focus},
    )


@app.post("/assistant/skills/document/extract-key-fields")
def assistant_skill_document_extract_key_fields(request: SkillDocumentKeyFieldsRequest) -> dict[str, Any]:
    return SkillRegistry().execute(
        "document_extract_key_fields",
        {"path": request.path, "document_type": request.document_type},
    )


@app.post("/assistant/skills/files/search-report")
def assistant_skill_file_search_report(request: SkillFileSearchReportRequest) -> dict[str, Any]:
    return SkillRegistry().execute(
        "file_search_report",
        {
            "query": request.query,
            "extensions": request.extensions,
            "content_search": request.content_search,
        },
    )


@app.post("/assistant/skills/files/index-excel")
def assistant_skill_document_index_excel(request: SkillDocumentIndexExcelRequest) -> dict[str, Any]:
    return SkillRegistry().execute(
        "document_index_excel",
        {"query": request.query, "extensions": request.extensions},
    )


@app.post("/assistant/skills/web/report")
def assistant_skill_web_report(request: SkillWebResearchRequest) -> dict[str, Any]:
    return SkillRegistry().execute("web_research_report", {"query": request.query})


@app.post("/assistant/skills/web/excel")
def assistant_skill_web_excel(request: SkillWebResearchRequest) -> dict[str, Any]:
    return SkillRegistry().execute("web_research_excel", {"query": request.query})


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
    model = llm.model_name()
    fast_model = llm.fast_model_name()
    smart_model = llm.smart_model_name()
    try:
        response = requests.get(tags_url, timeout=3)
        response.raise_for_status()
        models = response.json().get("models", [])
        installed_names = [str(item.get("name", "")) for item in models if item.get("name")]
        installed_model = next((item for item in models if item.get("name") == model), None)
        installed = installed_model is not None
        fast_installed = fast_model in installed_names
        smart_installed = smart_model in installed_names
        return {
            "provider": "ollama",
            "reachable": True,
            "model": model,
            "main_model": model,
            "fast_model": fast_model,
            "smart_model": smart_model,
            "base_url": base_url,
            "installed_models": installed_names,
            "configured_model_installed": installed,
            "configured_model_size_bytes": installed_model.get("size") if installed_model else None,
            "fast_model_installed": fast_installed,
            "smart_model_installed": smart_installed,
            "current_model_installed": installed,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "warmup_enabled": os.getenv("OLLAMA_WARMUP_ENABLED", "true").strip().lower() == "true",
            "warmup_on_startup": os.getenv("OLLAMA_WARMUP_ON_STARTUP", "true").strip().lower() == "true",
            "native_api_enabled": llm.native_ollama_enabled(),
            "last_benchmark": _last_native_benchmark,
            "complexity_routing_enabled": llm.complexity_routing_enabled(),
            "routing_mode": "complexity" if llm.complexity_routing_enabled() else "main_model",
            "benchmark_warning": None,
            "gpu_note": "GPU-Nutzung bitte mit `ollama ps` pruefen.",
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
            "main_model": model,
            "fast_model": fast_model,
            "smart_model": smart_model,
            "base_url": base_url,
            "installed_models": [],
            "configured_model_installed": False,
            "configured_model_size_bytes": None,
            "fast_model_installed": False,
            "smart_model_installed": False,
            "current_model_installed": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "warmup_enabled": os.getenv("OLLAMA_WARMUP_ENABLED", "true").strip().lower() == "true",
            "warmup_on_startup": os.getenv("OLLAMA_WARMUP_ON_STARTUP", "true").strip().lower() == "true",
            "native_api_enabled": llm.native_ollama_enabled(),
            "last_benchmark": _last_native_benchmark,
            "complexity_routing_enabled": llm.complexity_routing_enabled(),
            "routing_mode": "complexity" if llm.complexity_routing_enabled() else "main_model",
            "gpu_note": "GPU-Nutzung bitte mit `ollama ps` pruefen.",
            "message": "Ollama ist nicht erreichbar. Bitte starte Ollama und pruefe http://localhost:11434.",
        }


@app.get("/assistant/ollama/benchmark")
def assistant_ollama_benchmark() -> dict[str, Any]:
    llm = LLMClient()
    started = time.perf_counter()
    if llm.provider_name() != "ollama" or not llm.is_available():
        return {
            "provider": "ollama",
            "available": False,
            "reachable": False,
            "model": llm.model_name(),
            "duration_ms": 0,
            "response_time_ms": 0,
            "response_length": 0,
            "output_length": 0,
            "message": "Ollama ist nicht als lokaler LLM-Provider verfuegbar.",
        }
    try:
        response = llm.create_response_with_tools(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Antworte nur mit: OK"},
            ],
            [],
        )
        text = str(response.get("text") or "")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": "ollama",
            "available": True,
            "reachable": True,
            "model": llm.model_name(),
            "duration_ms": elapsed_ms,
            "response_time_ms": elapsed_ms,
            "response_length": len(text),
            "output_length": len(text),
            "warning": "Ollama antwortet langsam." if elapsed_ms > 5000 else None,
            "message": "Kurzer Ollama-Benchmark abgeschlossen.",
        }
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": "ollama",
            "available": False,
            "reachable": False,
            "model": llm.model_name(),
            "duration_ms": elapsed_ms,
            "response_time_ms": elapsed_ms,
            "response_length": 0,
            "output_length": 0,
            "message": "Ollama-Benchmark fehlgeschlagen. Bitte pruefe Ollama und das konfigurierte Modell.",
        }


@app.get("/assistant/ollama/benchmark/models")
def assistant_ollama_benchmark_models() -> dict[str, Any]:
    llm = LLMClient()
    status = assistant_ollama_status()
    installed = set(status.get("installed_models") or [])
    configured = []
    for model in (llm.fast_model_name(), llm.smart_model_name(), llm.model_name()):
        if model and model not in configured:
            configured.append(model)
    benchmarks: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if not status.get("reachable"):
        return {
            "provider": "ollama",
            "reachable": False,
            "benchmarks": [],
            "skipped_models": [{"model": model, "reason": "ollama_unreachable"} for model in configured],
            "message": "Ollama ist nicht erreichbar. Bitte starte Ollama und pruefe http://localhost:11434.",
        }
    for model in configured:
        if model not in installed:
            skipped.append({"model": model, "reason": "not_installed"})
            continue
        started = time.perf_counter()
        try:
            response = llm.create_response_with_tools(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Antworte nur mit: OK"},
                ],
                [],
                model=model,
            )
            text = str(response.get("text") or "")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            benchmarks.append(
                {
                    "model": model,
                    "duration_ms": elapsed_ms,
                    "reachable": True,
                    "output_length": len(text),
                    "warning": _ollama_speed_warning(model, elapsed_ms),
                }
            )
        except Exception:
            benchmarks.append(
                {
                    "model": model,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "reachable": False,
                    "output_length": 0,
                    "warning": "Benchmark fehlgeschlagen.",
                }
            )
    return {
        "provider": "ollama",
        "reachable": True,
        "benchmarks": benchmarks,
        "skipped_models": skipped,
        "message": "Ollama-Modellbenchmark abgeschlossen.",
    }


@app.get("/assistant/ollama/benchmark/native")
def assistant_ollama_benchmark_native(models: str = Query("current", pattern="^(current|fast|smart|all)$")) -> dict[str, Any]:
    global _last_native_benchmark
    llm = LLMClient()
    native = NativeOllamaClient()
    models_data = native.list_models()
    installed = set(models_data.get("installed_models") or [])
    benchmarks: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if not models_data.get("reachable"):
        return {
            "provider": "ollama",
            "reachable": False,
            "benchmarks": [],
            "skipped_models": [{"model": model, "reason": "ollama_unreachable"} for model in _selected_ollama_models(llm, models)],
            "message": "Ollama ist nicht erreichbar.",
        }
    for model in _selected_ollama_models(llm, models):
        if model not in installed:
            skipped.append({"model": model, "reason": "not_installed"})
            continue
        result = _sanitize_benchmark_result(native.benchmark_model(model))
        result["warning"] = result.get("warning") or _ollama_speed_warning(model, int(result.get("duration_ms") or 0))
        result["cold_start_likely"] = _cold_start_likely(result)
        benchmarks.append(result)
    response = {
        "provider": "ollama",
        "reachable": True,
        "benchmarks": benchmarks,
        "skipped_models": skipped,
        "message": "Native Ollama-Benchmarks abgeschlossen.",
    }
    _last_native_benchmark = response
    return response


@app.get("/assistant/ollama/benchmark/warm")
def assistant_ollama_benchmark_warm(model: str | None = None) -> dict[str, Any]:
    global _last_native_warm_benchmark
    llm = LLMClient()
    native = NativeOllamaClient()
    models_data = native.list_models()
    installed = set(models_data.get("installed_models") or [])
    if not models_data.get("reachable"):
        return {"provider": "ollama", "reachable": False, "message": "Ollama ist nicht erreichbar."}
    selected_model = model or (llm.fast_model_name() if llm.fast_model_name() in installed else llm.model_name())
    if selected_model not in installed:
        return {"provider": "ollama", "reachable": True, "model": selected_model, "message": "Kein konfiguriertes Modell ist installiert."}
    cold = _sanitize_benchmark_result(native.benchmark_model(selected_model))
    warm = _sanitize_benchmark_result(native.benchmark_model(selected_model))
    response = {
        "provider": "ollama",
        "reachable": True,
        "model": selected_model,
        "cold_result": {**cold, "cold_start_likely": _cold_start_likely(cold)},
        "warm_result": {**warm, "cold_start_likely": _cold_start_likely(warm)},
        "interpretation": _interpret_warm_benchmark(cold, warm),
    }
    _last_native_warm_benchmark = response
    return response


@app.get("/assistant/ollama/performance-advice")
def assistant_ollama_performance_advice() -> dict[str, Any]:
    status = assistant_ollama_status()
    llm = LLMClient()
    advice = [
        "Hammer Jarvis fuehrt das Modell nicht direkt aus. Ollama entscheidet lokal ueber CPU/GPU-Nutzung.",
        "Pruefe waehrend eines Benchmarks im Windows Task-Manager die GPU-Auslastung.",
        "Bei NVIDIA kann nvidia-smi helfen, falls es installiert ist.",
    ]
    if status.get("reachable") and not status.get("fast_model_installed"):
        advice.append(
            f"Das schnelle Modell {llm.fast_model_name()} ist nicht installiert. "
            "Installiere ein kleines Modell, wenn kurze Antworten schneller werden sollen."
        )
    if _last_native_warm_benchmark:
        cold = _last_native_warm_benchmark.get("cold_result", {})
        warm = _last_native_warm_benchmark.get("warm_result", {})
        if _cold_slow_warm_fast(cold, warm):
            advice.append("Cold Start ist das Hauptproblem. OLLAMA_KEEP_ALIVE und Warmup helfen.")
            if not llm.native_ollama_enabled():
                advice.append("Native Ollama-Benchmarks sind warm schnell. Setze bei Bedarf OLLAMA_USE_NATIVE_API=true.")
        elif int(warm.get("duration_ms") or 0) > 4000:
            advice.append("Auch der warme Benchmark ist langsam. Pruefe GPU/VRAM/Treiber oder teste llama3.2:1b.")
    for benchmark in (_last_native_benchmark or {}).get("benchmarks", []):
        measured = int(benchmark.get("measured_http_duration_ms") or benchmark.get("measured_total_duration_ms") or 0)
        ollama_duration = int(benchmark.get("ollama_total_duration_ms") or benchmark.get("total_duration_ms") or 0)
        if measured > ollama_duration + 1000:
            advice.append(
                "Jarvis misst noch deutlichen Overhead gegenueber Ollama. "
                "Pruefe NativeOllamaClient, HTTP-Client und Benchmark-Messbereich."
            )
            break
    if not llm.complexity_routing_enabled():
        advice.append("LLM_COMPLEXITY_ROUTING ist deaktiviert. Standardmaessig wird das Hauptmodell genutzt.")
    if status.get("fast_model_installed") and not _last_native_warm_benchmark:
        advice.append("Fuer eine konkrete Diagnose fuehre /assistant/ollama/benchmark/warm aus.")
    return {
        "provider": "ollama",
        "reachable": bool(status.get("reachable")),
        "main_model": llm.model_name(),
        "fast_model": llm.fast_model_name(),
        "smart_model": llm.smart_model_name(),
        "fast_model_installed": bool(status.get("fast_model_installed")),
        "smart_model_installed": bool(status.get("smart_model_installed")),
        "complexity_routing_enabled": llm.complexity_routing_enabled(),
        "native_api_enabled": llm.native_ollama_enabled(),
        "advice": advice,
    }


@app.get("/assistant/performance/status")
def assistant_performance_status() -> dict[str, Any]:
    return metrics_store.status()


@app.get("/assistant/performance/benchmark")
def assistant_performance_benchmark() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def run_check(name: str, category: str, fn: Any) -> None:
        started = time.perf_counter()
        try:
            result = fn()
            checks.append({"name": name, "category": category, "duration_ms": int((time.perf_counter() - started) * 1000), "success": True, "result": result})
        except Exception as exc:
            checks.append({"name": name, "category": category, "duration_ms": int((time.perf_counter() - started) * 1000), "success": False, "error": exc.__class__.__name__})

    run_check("entity_cache_status", "home_assistant", lambda: HomeAssistantEntityCatalog().status())
    def small_export_search() -> dict[str, Any]:
        previous = os.getenv("FILE_SEARCH_ALLOWED_DIRS")
        os.environ["FILE_SEARCH_ALLOWED_DIRS"] = str(Path(os.getenv("EXPORT_DIR", "workspace/exports")))
        try:
            return FileSearchTool().search_files("hauscheck", limit=3)
        finally:
            if previous is None:
                os.environ.pop("FILE_SEARCH_ALLOWED_DIRS", None)
            else:
                os.environ["FILE_SEARCH_ALLOWED_DIRS"] = previous

    run_check("small_file_search", "file_search", small_export_search)
    run_check("dashboard_route", "dashboard", lambda: {"route": "/dashboard", "exists": (STATIC_DIR / "dashboard.html").exists()})
    run_check("memory_search", "memory", lambda: MemoryStore().search_memory("hammer", limit=3))
    if LLMClient().provider_name() == "ollama" and LLMClient().is_available():
        run_check("ollama_tiny_prompt", "llm", lambda: assistant_ollama_benchmark())
    return {"checks": checks, "summary": {"count": len(checks), "errors": sum(1 for check in checks if not check["success"])}}


def _ollama_speed_warning(model: str, duration_ms: int) -> str | None:
    if duration_ms <= 4000:
        return None
    if model == os.getenv("OLLAMA_MODEL_SMART", os.getenv("OLLAMA_MODEL", "qwen3:8b")):
        return (
            "qwen3:8b ist fuer kurze Antworten langsam. Fuer schnelle "
            "Alltagsantworten kann ein kleineres Modell als OLLAMA_MODEL_FAST genutzt werden."
        )
    return "Dieses Modell antwortet langsam."


def _configured_ollama_models(llm: LLMClient) -> list[str]:
    models: list[str] = []
    for model in (llm.model_name(), llm.fast_model_name(), llm.smart_model_name()):
        if model and model not in models:
            models.append(model)
    return models


def _selected_ollama_models(llm: LLMClient, selection: str) -> list[str]:
    if selection == "fast":
        return [llm.fast_model_name()]
    if selection == "smart":
        return [llm.smart_model_name()]
    if selection == "all":
        return _configured_ollama_models(llm)
    return [llm.model_name()]


def _sanitize_benchmark_result(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "model",
        "text",
        "output_length",
        "done",
        "done_reason",
        "total_duration_ms",
        "load_duration_ms",
        "prompt_eval_duration_ms",
        "eval_duration_ms",
        "ollama_total_duration_ms",
        "prompt_eval_count",
        "eval_count",
        "measured_http_duration_ms",
        "measured_total_duration_ms",
        "duration_ms",
        "warning",
        "cold_start_likely",
    }
    return {key: result[key] for key in allowed if key in result}


def _cold_start_likely(result: dict[str, Any]) -> bool:
    duration = int(result.get("duration_ms") or result.get("total_duration_ms") or 0)
    load = int(result.get("load_duration_ms") or 0)
    return duration > 1000 and load > 0 and load >= int(duration * 0.5)


def _cold_slow_warm_fast(cold: dict[str, Any], warm: dict[str, Any]) -> bool:
    return int(cold.get("duration_ms") or 0) > 4000 and int(warm.get("duration_ms") or 0) <= 1500


def _interpret_warm_benchmark(cold: dict[str, Any], warm: dict[str, Any]) -> str:
    if _cold_slow_warm_fast(cold, warm):
        return "Cold Start ist das Hauptproblem. keep_alive/warmup hilft."
    if int(cold.get("duration_ms") or 0) > 4000 and int(warm.get("duration_ms") or 0) > 4000:
        return "Ollama selbst ist trotz GPU langsam oder Hardware/VRAM ist begrenzt."
    return "Lokale LLM-Performance ist nutzbar."


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


@app.get("/assistant/memory/status")
def assistant_memory_status() -> dict[str, Any]:
    store = MemoryStore()
    data = store.list_memory(limit=1_000_000)
    return {
        "enabled": os.getenv("MEMORY_ENABLED", "true").strip().lower() == "true",
        "count": data.get("count", 0),
        "file": str(store.path),
        "file_exists": store.path.exists(),
    }


@app.get("/assistant/memory")
def assistant_memory_list(type: str | None = None, tag: str | None = None, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    return MemoryStore().list_memory(type=type, tag=tag, limit=limit)


@app.get("/assistant/memory/search")
def assistant_memory_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    return MemoryStore().search_memory(q, limit=limit)


@app.post("/assistant/memory")
def assistant_memory_create(request: MemoryCreateRequest) -> dict[str, Any]:
    classification = MemoryClassifier().classify_text(f"{request.key} {request.value}")
    if classification.get("blocked"):
        return classification
    return MemoryStore().add_memory(request.model_dump())


@app.patch("/assistant/memory/{memory_id}")
def assistant_memory_update(memory_id: str, request: MemoryPatchRequest) -> dict[str, Any]:
    patch = {key: value for key, value in request.model_dump().items() if value is not None}
    return MemoryStore().update_memory(memory_id, patch)


@app.delete("/assistant/memory/{memory_id}")
def assistant_memory_delete(memory_id: str) -> dict[str, Any]:
    return MemoryStore().delete_memory(memory_id)


@app.post("/assistant/memory/repair")
def assistant_memory_repair(request: MemoryRepairRequest) -> dict[str, Any]:
    return MemoryStore().repair_memory_values(dry_run=request.dry_run)


@app.post("/assistant/memory/export")
def assistant_memory_export() -> dict[str, Any]:
    return MemoryStore().export_memory()


@app.get("/assistant/knowledge/status")
def assistant_knowledge_status() -> dict[str, Any]:
    store = KnowledgeStore()
    result = store.status()
    documents = store.list_documents().get("documents", [])
    extractor_status = {
        "pdf": True,
        "docx": True,
        "xlsx": True,
        "xlsm": True,
        "csv": True,
        "txt": True,
        "md": True,
        "json": True,
        "ocr": False,
    }
    return {
        **result,
        "data_dir": str(store.path.parent),
        "upload_dir": str(store.upload_dir),
        "store_file": str(store.path),
        "document_count": len(documents),
        "chunk_count": int(result.get("chunk_count", 0)),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in documents),
        "supported_extensions": sorted(SUPPORTED_KNOWLEDGE_EXTENSIONS),
        "max_upload_mb": max(1, max_upload_bytes() // (1024 * 1024)),
        "embedding_enabled": False,
        "search_mode": "keyword",
        "extractor_status": extractor_status,
        "extractor_availability": extractor_status,
    }


@app.post("/assistant/knowledge/index")
def assistant_knowledge_index(request: KnowledgeIndexRequest) -> dict[str, Any]:
    store = KnowledgeStore()
    path = Path(request.path)
    if path.is_dir() and request.recursive:
        return store.index_directory(path)
    return store.index_text_file(path)


@app.get("/assistant/knowledge/search")
def assistant_knowledge_search(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=50)) -> dict[str, Any]:
    return KnowledgeStore().search_knowledge(q, limit=limit)


@app.get("/assistant/knowledge/documents")
def assistant_knowledge_documents() -> dict[str, Any]:
    return KnowledgeStore().list_documents()


@app.post("/assistant/knowledge/upload")
async def assistant_knowledge_upload(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    """Store and index each local upload independently without retaining request files."""

    store = KnowledgeStore()
    documents: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    success_count = 0
    maximum_bytes = max_upload_bytes()

    for upload in files:
        started = time.perf_counter()
        raw_filename = str(upload.filename or "")
        display_name = Path(raw_filename.replace("\\", "/")).name
        size_bytes = 0
        content: bytes | bytearray | None = None
        content_buffer: bytearray | None = None
        document_id: str | None = None
        extension = Path(display_name).suffix.lower()
        duplicate = False
        reason: str | None = None
        success = False
        try:
            content_buffer = bytearray()
            while True:
                block = await upload.read(KNOWLEDGE_UPLOAD_READ_CHUNK_BYTES)
                if not block:
                    break
                size_bytes += len(block)
                if size_bytes > maximum_bytes:
                    reason = "file_too_large"
                    break
                content_buffer.extend(block)
            if reason is None:
                content = content_buffer
                stored = store.store_upload(raw_filename, content, upload.content_type)
                content_buffer.clear()
                content = None
                document = stored.get("document")
                if isinstance(document, dict):
                    document_id = str(document.get("document_id") or "") or None
                duplicate = bool(stored.get("duplicate"))
                if not stored.get("stored"):
                    reason = str(stored.get("reason") or "upload_write_failed")
                elif duplicate:
                    success = True
                    success_count += 1
                    documents.append(_knowledge_upload_document(document, duplicate=True))
                else:
                    indexed = store.reindex_document(document_id or "")
                    if indexed.get("indexed"):
                        success = True
                        success_count += 1
                        documents.append(_knowledge_upload_document(indexed.get("document"), duplicate=False))
                    elif indexed.get("reason") == "ocr_required":
                        # A valid image-only PDF is stored successfully; OCR is intentionally not available in v1.
                        success = True
                        success_count += 1
                        documents.append(
                            _knowledge_upload_document(
                                document,
                                duplicate=False,
                                extraction_status="ocr_required",
                                extraction_message=str(indexed.get("message") or "OCR wird noch nicht unterstützt."),
                            )
                        )
                    else:
                        reason = str(indexed.get("reason") or "index_write_failed")
            if reason is not None:
                errors.append(
                    {
                        "filename": display_name,
                        "name": display_name,
                        "reason": reason,
                        "status_code": _knowledge_error_status(reason),
                        "message": _knowledge_reason_message(reason),
                    }
                )
        except Exception:
            reason = "upload_write_failed"
            errors.append(
                {
                    "filename": display_name,
                    "name": display_name,
                    "reason": reason,
                    "status_code": _knowledge_error_status(reason),
                    "message": _knowledge_reason_message(reason),
                }
            )
        finally:
            await upload.close()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            write_audit_log(
                "knowledge_upload",
                {
                    "operation": "upload",
                    "document_id": document_id,
                    "extension": extension,
                    "size_bytes": size_bytes,
                    "duplicate": duplicate,
                    "success": success,
                    "reason": reason,
                    "duration_ms": elapsed_ms,
                },
            )
            del content
            if content_buffer is not None:
                content_buffer.clear()

    return {
        "uploaded": success_count > 0,
        "success_count": success_count,
        "failed_count": len(errors),
        "documents": documents,
        "errors": errors,
    }


@app.get("/assistant/knowledge/documents/{document_id}")
def assistant_knowledge_document_detail(document_id: str) -> dict[str, Any]:
    store = KnowledgeStore()
    found = store.get_document(document_id)
    if not found.get("found"):
        _raise_knowledge_error(str(found.get("reason") or "document_not_found"))
    chunks = store.get_document_chunks(document_id)
    if chunks.get("error"):
        _raise_knowledge_error(str(chunks.get("reason") or "index_recovery_failed"))
    return {
        "document": _public_knowledge_document(found.get("document")),
        "chunk_count": int(chunks.get("count") or 0),
        "chunks": [
            _public_knowledge_chunk(document_id, item, fallback_index)
            for fallback_index, item in enumerate(
                list(chunks.get("chunks") or [])[:KNOWLEDGE_DETAIL_PREVIEW_COUNT]
            )
        ],
    }


@app.post("/assistant/knowledge/documents/{document_id}/reindex")
def assistant_knowledge_reindex_document(document_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    store = KnowledgeStore()
    result = store.reindex_document(document_id)
    write_audit_log(
        "knowledge_reindex",
        {
            "operation": "reindex",
            "document_id": document_id,
            "extension": _knowledge_document_extension(store, document_id),
            "success": bool(result.get("indexed")),
            "reason": result.get("reason"),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    if not result.get("indexed") and result.get("reason") != "ocr_required":
        _raise_knowledge_error(str(result.get("reason") or "index_write_failed"))
    document = result.get("document")
    if not isinstance(document, dict) and result.get("reason") == "ocr_required":
        document = store.get_document(document_id).get("document")
    return {
        "indexed": bool(result.get("indexed")),
        "document": _public_knowledge_document(document),
        "chunk_count": int(result.get("chunk_count") or 0),
        "reason": result.get("reason"),
        "message": result.get("message"),
    }


@app.delete("/assistant/knowledge/documents/{document_id}")
def assistant_knowledge_delete_document(document_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    store = KnowledgeStore()
    extension = _knowledge_document_extension(store, document_id)
    result = store.delete_document(document_id)
    write_audit_log(
        "knowledge_delete",
        {
            "operation": "delete",
            "document_id": document_id,
            "extension": extension,
            "success": bool(result.get("deleted")),
            "reason": result.get("reason"),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    if not result.get("deleted"):
        _raise_knowledge_error(str(result.get("reason") or "document_not_found"))
    return {
        "deleted": True,
        "physical_file_deleted": bool(result.get("physical_file_deleted")),
        "cleanup_pending": bool(result.get("cleanup_pending")),
        "document_id": document_id,
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


def _knowledge_upload_document(
    document: Any,
    *,
    duplicate: bool,
    extraction_status: str | None = None,
    extraction_message: str | None = None,
) -> dict[str, Any]:
    payload = _public_knowledge_document(document)
    payload["duplicate"] = duplicate
    if extraction_status is not None:
        payload["extraction_status"] = extraction_status
    if extraction_message is not None:
        payload["extraction_message"] = extraction_message
    return payload


def _public_knowledge_document(document: Any) -> dict[str, Any]:
    """Return required document metadata, including local path, without chunk text or binaries."""

    if not isinstance(document, dict):
        return {}
    allowed = (
        "document_id",
        "name",
        "original_name",
        "stored_name",
        "extension",
        "mime_type",
        "size_bytes",
        "sha256",
        "uploaded_at",
        "indexed_at",
        "modified_at",
        "chunk_count",
        "extraction_status",
        "extraction_message",
        "source_type",
        "path",
    )
    return {key: document[key] for key in allowed if key in document}


def _public_knowledge_chunk(document_id: str, chunk: Any, fallback_index: int) -> dict[str, Any]:
    item = chunk if isinstance(chunk, dict) else {}
    try:
        index = int(item.get("index", fallback_index))
    except (TypeError, ValueError):
        index = fallback_index
    return {
        "chunk_id": str(item.get("chunk_id") or f"{document_id}:{index}"),
        "index": index,
        "chunk_index": index,
        "preview": str(item.get("text") or "")[:KNOWLEDGE_DETAIL_PREVIEW_CHARS],
    }


def _knowledge_document_extension(store: KnowledgeStore, document_id: str) -> str | None:
    result = store.get_document(document_id)
    document = result.get("document")
    return str(document.get("extension")) if isinstance(document, dict) and document.get("extension") else None


def _raise_knowledge_error(reason: str) -> None:
    raise HTTPException(
        status_code=_knowledge_error_status(reason),
        detail={"reason": reason, "message": _knowledge_reason_message(reason)},
    )


def _knowledge_error_status(reason: str) -> int:
    return {
        "document_not_found": 404,
        "source_file_missing": 409,
        "invalid_filename": 400,
        "unsafe_upload_path": 400,
        "unsafe_pending_delete_path": 400,
        "unsupported_file_type": 415,
        "invalid_pdf_header": 400,
        "empty_file": 400,
        "empty_or_placeholder_file": 400,
        "file_too_large": 413,
        "index_recovery_failed": 500,
        "index_write_failed": 500,
        "upload_write_failed": 500,
    }.get(reason, 500)


def _knowledge_reason_message(reason: str) -> str:
    messages = {
        "document_not_found": "Das Dokument wurde nicht gefunden.",
        "source_file_missing": "Die lokale Quelldatei ist nicht mehr verfügbar.",
        "invalid_filename": "Der Dateiname ist ungültig.",
        "unsafe_upload_path": "Der angegebene Dateipfad ist nicht zulässig.",
        "unsafe_pending_delete_path": "Der lokale Dateipfad ist nicht zulässig.",
        "unsupported_file_type": "Dieser Dateityp wird nicht unterstützt.",
        "invalid_pdf_header": "Die Datei hat keine gültige PDF-Signatur.",
        "empty_file": "Die Datei ist leer.",
        "empty_or_placeholder_file": "Die Datei ist leer oder nur ein lokaler Platzhalter.",
        "file_too_large": "Die Datei überschreitet die zulässige Uploadgröße.",
        "ocr_required": "Das PDF enthält keinen extrahierbaren Text. OCR wird noch nicht unterstützt.",
        "index_recovery_failed": "Der lokale Wissensindex kann nicht sicher gelesen werden.",
        "index_write_failed": "Der lokale Wissensindex konnte nicht geschrieben werden.",
        "upload_write_failed": "Die Datei konnte nicht lokal gespeichert werden.",
    }
    return messages.get(reason, "Die Dokumentverarbeitung konnte nicht sicher abgeschlossen werden.")


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
