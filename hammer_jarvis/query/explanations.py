from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hammer_jarvis.understanding.models import UnderstandingRelationship


def relationship_id(relationship: UnderstandingRelationship) -> str:
    raw = f"{relationship.source_id}|{relationship.type}|{relationship.target_id}"
    return f"relationship:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


class RelationshipExplainer:
    def explain(
        self,
        relationship: UnderstandingRelationship,
        objects: dict[str, dict[str, Any]],
        *,
        include_evidence: bool = True,
    ) -> dict[str, Any]:
        source = objects.get(relationship.source_id, {})
        target = objects.get(relationship.target_id, {})
        source_type = str(source.get("type") or "EngineeringObject")
        target_type = str(target.get("type") or "EngineeringObject")
        source_name = str(source.get("name") or relationship.source_id)
        target_name = str(target.get("name") or relationship.target_id)
        reason = _reason(relationship.type, source_type, target_type)
        payload: dict[str, Any] = {
            "id": relationship_id(relationship),
            "relationship": relationship.type,
            "source_id": relationship.source_id,
            "target_id": relationship.target_id,
            "source": source_name,
            "target": target_name,
            "reason": reason,
            "metadata": _safe_metadata(relationship.metadata),
        }
        if include_evidence:
            payload["evidence"] = {
                "existing_edge": True,
                "source_type": source_type,
                "target_type": target_type,
                "items": list(relationship.evidence),
            }
        return payload


def _reason(relationship_type: str, source_type: str, target_type: str) -> str:
    if relationship_type == "CONTAINS":
        return f"Der {source_type}-Knoten enthaelt diesen {target_type}-Knoten."
    if relationship_type == "DEFINES":
        return f"Der {source_type}-Knoten definiert diesen {target_type}-Knoten."
    if relationship_type == "AFFECTS":
        return f"Der {source_type}-Knoten betrifft diesen {target_type}-Knoten."
    if relationship_type == "REFERENCES":
        return f"Der {source_type}-Knoten referenziert diesen {target_type}-Knoten."
    if relationship_type == "RELATES_TO":
        return f"Der {source_type}-Knoten ist mit diesem {target_type}-Knoten verbunden."
    return "Diese Beziehung ist im Engineering Understanding Report vorhanden."


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            safe[key] = None
        elif key in {"path", "source_file", "file"}:
            safe[key] = Path(str(value)).name
        else:
            safe[key] = value
    return safe
