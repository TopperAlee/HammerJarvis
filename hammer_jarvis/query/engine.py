from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from hammer_jarvis.diagnostics.models import DiagnosticReport
from hammer_jarvis.documents.models import Document
from hammer_jarvis.engineering.graph import EngineeringGraph
from hammer_jarvis.query.explanations import RelationshipExplainer, relationship_id
from hammer_jarvis.query.models import (
    EngineeringQueryMatch,
    EngineeringQueryRequest,
    EngineeringQueryResult,
    EngineeringQueryType,
    ParsedEngineeringQuery,
)
from hammer_jarvis.query.parser import EngineeringQueryParser
from hammer_jarvis.research.answer_engine import ResearchLLM
from hammer_jarvis.understanding.models import EngineeringUnderstandingReport, UnderstandingRelationship


class EngineeringQueryError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class EngineeringQueryEngine:
    def __init__(
        self,
        *,
        graph: EngineeringGraph,
        understanding: EngineeringUnderstandingReport | None,
        objects: dict[str, dict[str, Any]],
        diagnostics: DiagnosticReport | None = None,
        documents: list[Document] | None = None,
        parser: EngineeringQueryParser | None = None,
        answer_builder: "EngineeringCopilotAnswerBuilder | None" = None,
    ) -> None:
        self.graph = graph
        self.understanding = understanding
        self.objects = {key: _safe_object(value) for key, value in objects.items()}
        self.diagnostics = diagnostics
        self.documents = documents or []
        self.parser = parser or EngineeringQueryParser()
        self.explainer = RelationshipExplainer()
        self.answer_builder = answer_builder or EngineeringCopilotAnswerBuilder()

    def execute(self, request: EngineeringQueryRequest) -> EngineeringQueryResult:
        if self.understanding is None:
            raise EngineeringQueryError("Engineering Understanding wurde noch nicht aufgebaut.", 409)
        parsed = self.parser.parse(request.query)
        result = self._execute_parsed(request, parsed)
        result.answer = self.answer_builder.build(result)
        return result

    def object_lookup(self, object_id: str) -> EngineeringQueryResult:
        if self.understanding is None:
            raise EngineeringQueryError("Engineering Understanding wurde noch nicht aufgebaut.", 409)
        if object_id not in self.objects:
            raise EngineeringQueryError("Engineering object not found.", 404)
        request = EngineeringQueryRequest(query=f"finde objekt {object_id}", object_id=object_id)
        return self._execute_parsed(
            request,
            ParsedEngineeringQuery(query_type=EngineeringQueryType.OBJECT_SEARCH, search_text=object_id),
        )

    def explain_relationship(self, relationship_identifier: str) -> dict[str, Any]:
        if self.understanding is None:
            raise EngineeringQueryError("Engineering Understanding wurde noch nicht aufgebaut.", 409)
        relationship = self._relationship_by_id(relationship_identifier)
        if relationship is None:
            raise EngineeringQueryError("Engineering relationship not found.", 404)
        return self.explainer.explain(relationship, self.objects)

    def _execute_parsed(self, request: EngineeringQueryRequest, parsed: ParsedEngineeringQuery) -> EngineeringQueryResult:
        matched_objects: list[EngineeringQueryMatch] = []
        relationships: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        explanations: list[dict[str, Any]] = []

        target_text = request.object_id or parsed.search_text
        if parsed.query_type == EngineeringQueryType.UNKNOWN:
            recommendations = ["Projekt oder Suchbegriff pruefen"]
        elif parsed.query_type == EngineeringQueryType.LIST_OBJECT_TYPE:
            matched_objects = self._matches_by_type(parsed.object_type, request.limit)
            recommendations = self._recommendations(matched_objects, diagnostics, documents, parsed.query_type)
        elif parsed.query_type == EngineeringQueryType.ORPHANS:
            matched_objects = self._orphan_matches(request.limit)
            recommendations = self._recommendations(matched_objects, diagnostics, documents, parsed.query_type)
        elif parsed.query_type == EngineeringQueryType.EXPLAIN_RELATIONSHIP and parsed.relationship_id:
            explanation = self.explain_relationship(parsed.relationship_id)
            explanations = [explanation]
            relationships = [explanation]
            recommendations = []
        else:
            matched_objects = self._search_objects(target_text, request.limit)
            object_ids = [item.object_id for item in matched_objects]
            object_not_found = bool(target_text) and parsed.query_type in {
                EngineeringQueryType.OBJECT_SEARCH,
                EngineeringQueryType.RELATIONSHIPS,
                EngineeringQueryType.USAGE,
                EngineeringQueryType.DIAGNOSTICS,
                EngineeringQueryType.DOCUMENTS,
            } and not matched_objects
            if parsed.query_type in {EngineeringQueryType.RELATIONSHIPS, EngineeringQueryType.USAGE}:
                relationships = self._relationship_payloads(object_ids, parsed.query_type, request.include_evidence, request.limit)
                explanations = [item["explanation"] for item in relationships if "explanation" in item]
            if parsed.query_type == EngineeringQueryType.DIAGNOSTICS or request.include_diagnostics:
                diagnostics = self._diagnostics_for(object_ids, request.limit)
            if parsed.query_type == EngineeringQueryType.DOCUMENTS or request.include_documents:
                documents = self._documents_for(object_ids, request.project_id, request.limit)
            recommendations = self._recommendations(matched_objects, diagnostics, documents, parsed.query_type)
            if object_not_found:
                recommendations = ["Projekt oder Suchbegriff pruefen"]

        statistics = {
            "object_count": len(matched_objects),
            "relationship_count": len(relationships),
            "diagnostic_count": len(diagnostics),
            "document_count": len(documents),
            "limit": request.limit,
            "read_only": True,
        }
        if "object_not_found" in locals() and object_not_found:
            statistics["reason"] = "OBJECT_NOT_FOUND"
        return EngineeringQueryResult(
            query=request.query,
            query_type=parsed.query_type,
            matched_objects=matched_objects,
            relationships=relationships,
            diagnostics=diagnostics,
            documents=documents,
            explanations=explanations,
            recommendations=recommendations,
            statistics=statistics,
            status="OBJECT_NOT_FOUND" if "object_not_found" in locals() and object_not_found else "OK",
            error_code="OBJECT_NOT_FOUND" if "object_not_found" in locals() and object_not_found else None,
        )

    def _search_objects(self, search_text: str, limit: int) -> list[EngineeringQueryMatch]:
        if not search_text:
            return []
        normalized = search_text.lower()
        matches: list[EngineeringQueryMatch] = []
        for object_id, item in self.objects.items():
            haystack = " ".join(
                [
                    object_id,
                    str(item.get("name") or ""),
                    str(item.get("type") or ""),
                    str(item.get("source_file") or ""),
                    " ".join(str(value) for value in dict(item.get("metadata") or {}).values()),
                ]
            ).lower()
            if normalized not in haystack:
                continue
            score = 1.0 if normalized == object_id.lower() else 0.8 if normalized in str(item.get("name") or "").lower() else 0.5
            matches.append(_match(object_id, item, score))
        return _sort_matches(matches)[:limit]

    def _matches_by_type(self, object_type: str | None, limit: int) -> list[EngineeringQueryMatch]:
        if not object_type:
            return []
        matches = [
            _match(object_id, item, 0.9)
            for object_id, item in self.objects.items()
            if _type_matches(str(item.get("type") or ""), object_type)
        ]
        return _sort_matches(matches)[:limit]

    def _orphan_matches(self, limit: int) -> list[EngineeringQueryMatch]:
        orphan_ids = {str(item.get("id")) for item in self.understanding.orphan_objects} if self.understanding else set()
        matches = [_match(object_id, self.objects[object_id], 0.9) for object_id in orphan_ids if object_id in self.objects]
        return _sort_matches(matches)[:limit]

    def _relationship_payloads(
        self,
        object_ids: list[str],
        query_type: EngineeringQueryType,
        include_evidence: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        relationships = sorted(
            self.understanding.relationships if self.understanding else [],
            key=lambda item: (item.source_id, item.type, item.target_id),
        )
        for relationship in relationships:
            if query_type == EngineeringQueryType.USAGE:
                if relationship.target_id not in object_ids:
                    continue
            elif relationship.source_id not in object_ids and relationship.target_id not in object_ids:
                continue
            direction = "outgoing" if relationship.source_id in object_ids else "incoming"
            explanation = self.explainer.explain(relationship, self.objects, include_evidence=include_evidence)
            payloads.append(
                {
                    "id": relationship_id(relationship),
                    "source_id": relationship.source_id,
                    "target_id": relationship.target_id,
                    "type": relationship.type,
                    "direction": direction,
                    "metadata": _safe_metadata(relationship.metadata),
                    "explanation": explanation,
                }
            )
            if len(payloads) >= limit:
                break
        return payloads

    def _diagnostics_for(self, object_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if self.diagnostics is None:
            return []
        source_files = {str(self.objects[item].get("source_file") or "") for item in object_ids if item in self.objects}
        results = []
        for issue in self.diagnostics.issues:
            if issue.affected_object_id not in object_ids and (issue.source_file or "") not in source_files:
                continue
            payload = asdict(issue)
            payload["source_file"] = _basename(payload.get("source_file"))
            results.append(payload)
        return sorted(results, key=lambda item: (item.get("severity"), item.get("rule_id"), item.get("id")))[:limit]

    def _documents_for(self, object_ids: list[str], project_id: str | None, limit: int) -> list[dict[str, Any]]:
        document_ids = {item for item in object_ids if item.startswith("document:")}
        if self.understanding is not None:
            for relationship in self.understanding.relationships:
                if relationship.source_id in object_ids or relationship.target_id in object_ids or project_id:
                    if relationship.target_id.startswith("document:"):
                        document_ids.add(relationship.target_id)
                    if relationship.source_id.startswith("document:"):
                        document_ids.add(relationship.source_id)
        results = []
        for document in self.documents:
            if project_id or document.id in document_ids:
                results.append(_document_payload(document))
        return sorted(results, key=lambda item: (item["filename"], item["id"]))[:limit]

    def _relationship_by_id(self, relationship_identifier: str) -> UnderstandingRelationship | None:
        for relationship in self.understanding.relationships if self.understanding else []:
            if relationship_id(relationship) == relationship_identifier:
                return relationship
        return None

    def _recommendations(
        self,
        matches: list[EngineeringQueryMatch],
        diagnostics: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        query_type: EngineeringQueryType,
    ) -> list[str]:
        recommendations: list[str] = []
        if diagnostics:
            recommendations.append("Diagnosen zu diesem Objekt pruefen")
        if documents:
            recommendations.append("Zugehoerige Dokumentation oeffnen")
        if query_type == EngineeringQueryType.ORPHANS and matches:
            recommendations.append("Verwaiste Engineering-Objekte pruefen")
        if not matches and not diagnostics and not documents:
            recommendations.append("Projekt oder Suchbegriff pruefen")
        return recommendations


class EngineeringCopilotAnswerBuilder:
    def __init__(self, llm: ResearchLLM | None = None) -> None:
        self.llm = llm

    def build(self, result: EngineeringQueryResult) -> str:
        if not self._has_evidence(result):
            return self._fallback(result)
        prompt = self._prompt(result)
        if self.llm is None:
            return self._fallback(result)
        try:
            answer = self.llm.generate(prompt).strip()
        except Exception:
            return self._fallback(result)
        return answer or self._fallback(result)

    def _has_evidence(self, result: EngineeringQueryResult) -> bool:
        return bool(result.matched_objects or result.relationships or result.diagnostics or result.documents or result.explanations)

    def _fallback(self, result: EngineeringQueryResult) -> str:
        if result.query_type == EngineeringQueryType.UNKNOWN:
            return "Ich kann diese Engineering-Frage noch nicht regelbasiert auswerten."
        if result.error_code == "OBJECT_NOT_FOUND":
            return "Ich habe kein passendes Engineering-Objekt gefunden. Bitte pruefe Projekt oder Suchbegriff."
        parts = [
            f"Query-Typ: {result.query_type.value}.",
            f"Objekte: {len(result.matched_objects)}.",
            f"Beziehungen: {len(result.relationships)}.",
            f"Diagnosen: {len(result.diagnostics)}.",
            f"Dokumente: {len(result.documents)}.",
        ]
        if result.recommendations:
            parts.append("Empfehlung: " + result.recommendations[0] + ".")
        return " ".join(parts)

    def _prompt(self, result: EngineeringQueryResult) -> str:
        return (
            "Formuliere eine knappe Engineering-Copilot-Antwort ausschliesslich aus diesen strukturierten Daten.\n"
            f"Benutzerfrage: {result.query}\n"
            f"Query-Typ: {result.query_type.value}\n"
            f"Objekte: {[item.model_dump() for item in result.matched_objects]}\n"
            f"Beziehungen: {result.relationships}\n"
            f"Diagnosen: {result.diagnostics}\n"
            f"Dokumente: {result.documents}\n"
            f"Evidence: {result.explanations}\n"
        )


def _match(object_id: str, item: dict[str, Any], score: float) -> EngineeringQueryMatch:
    return EngineeringQueryMatch(
        object_id=object_id,
        object_type=str(item.get("type") or "EngineeringObject"),
        name=str(item.get("name") or object_id),
        score=score,
        source=_basename(item.get("source_file")),
        metadata=_safe_metadata(dict(item.get("metadata") or {})),
    )


def _sort_matches(matches: Iterable[EngineeringQueryMatch]) -> list[EngineeringQueryMatch]:
    return sorted(matches, key=lambda item: (-item.score, item.object_type, item.name.lower(), item.object_id))


def _type_matches(actual: str, expected: str) -> bool:
    if expected == "Document":
        return actual in {"Document", "Manual", "Specification", "Spreadsheet", "Image"}
    return actual == expected


def _safe_object(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    payload["source_file"] = _basename(payload.get("source_file"))
    payload["metadata"] = _safe_metadata(dict(payload.get("metadata") or {}))
    return payload


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"path", "source_file", "file"}:
            safe[key] = _basename(value)
        else:
            safe[key] = value
    return safe


def _document_payload(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.filename,
        "type": document.type,
        "mime_type": document.mime_type,
        "size": document.size,
        "modified_at": document.modified_at,
        "metadata": _safe_metadata(document.metadata),
    }


def _basename(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return Path(str(value).replace("\\", "/")).name
