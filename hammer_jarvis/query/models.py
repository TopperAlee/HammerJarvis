from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EngineeringQueryType(StrEnum):
    OBJECT_SEARCH = "OBJECT_SEARCH"
    RELATIONSHIPS = "RELATIONSHIPS"
    USAGE = "USAGE"
    DIAGNOSTICS = "DIAGNOSTICS"
    DOCUMENTS = "DOCUMENTS"
    ORPHANS = "ORPHANS"
    EXPLAIN_RELATIONSHIP = "EXPLAIN_RELATIONSHIP"
    LIST_OBJECT_TYPE = "LIST_OBJECT_TYPE"
    UNKNOWN = "UNKNOWN"


class EngineeringQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    object_id: str | None = None
    project_id: str | None = None
    include_diagnostics: bool = True
    include_documents: bool = True
    include_evidence: bool = True
    limit: int = 50

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query must not be empty.")
        return value

    @field_validator("limit")
    @classmethod
    def limit_must_be_valid(cls, value: int) -> int:
        if value < 1 or value > 500:
            raise ValueError("Limit must be between 1 and 500.")
        return value


class EngineeringQueryMatch(BaseModel):
    object_id: str
    object_type: str
    name: str
    score: float
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedEngineeringQuery(BaseModel):
    query_type: EngineeringQueryType
    search_text: str = ""
    object_type: str | None = None
    relationship_id: str | None = None
    message: str = ""


class EngineeringQueryResult(BaseModel):
    query: str
    query_type: EngineeringQueryType
    matched_objects: list[EngineeringQueryMatch] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    explanations: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    answer: str = ""
    status: str = "OK"
    error_code: str | None = None
