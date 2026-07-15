from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class EngineeringObjectType:
    PROJECT = "Project"
    PROJECT_FILE = "ProjectFile"
    TEXT_RESOURCE = "TextResource"
    DOCUMENT = "Document"
    MANUAL = "Manual"
    SPECIFICATION = "Specification"
    PANEL = "Panel"
    SCREEN = "Screen"
    ALARM = "Alarm"
    VARIABLE = "Variable"
    TRANSLATION = "Translation"
    DIAGNOSTIC = "Diagnostic"
    KNOWLEDGE_REFERENCE = "KnowledgeReference"


class UnderstandingRelationshipType:
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    AFFECTS = "AFFECTS"
    RELATES_TO = "RELATES_TO"
    REFERENCES = "REFERENCES"


@dataclass
class UnderstandingRelationship:
    source_id: str
    target_id: str
    type: str
    evidence: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineeringUnderstandingReport:
    generated_at: str
    object_count: int
    relationship_count: int
    object_types: dict[str, int]
    relationship_types: dict[str, int]
    orphan_objects: list[dict[str, Any]]
    relationships: list[UnderstandingRelationship]
    summary: str
    read_only: bool = True

    @classmethod
    def build(
        cls,
        *,
        object_count: int,
        relationships: list[UnderstandingRelationship],
        object_types: dict[str, int],
        relationship_types: dict[str, int],
        orphan_objects: list[dict[str, Any]],
    ) -> "EngineeringUnderstandingReport":
        return cls(
            generated_at=datetime.now(timezone.utc).isoformat(),
            object_count=object_count,
            relationship_count=len(relationships),
            object_types=object_types,
            relationship_types=relationship_types,
            orphan_objects=orphan_objects,
            relationships=relationships,
            summary=(
                f"Engineering-Modell aufgebaut: {object_count} Objekte, "
                f"{len(relationships)} begruendete Beziehungen, {len(orphan_objects)} Waisenobjekte."
            ),
        )
