from typing import Any

from pydantic import BaseModel, Field


class IntentRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "api"
    context: dict[str, Any] = Field(default_factory=dict)


class IntentResult(BaseModel):
    intent: str
    confidence: float
    source: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    risk: str = "GREEN"
    message: str = ""


class Capability(BaseModel):
    id: str
    name: str
    module: str
    plugin: str | None = None
    status: str
    implemented_since: str
    gui_available: bool
    api_available: bool
    voice_ready: bool
    risk_level: str
    read_only: bool


class ContextState(BaseModel):
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
    diagnostic_issue_count: int | None = None
    diagnostic_warning_count: int | None = None
    diagnostic_critical_count: int | None = None
    updated_at: str | None = None
