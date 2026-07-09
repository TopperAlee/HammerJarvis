from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from hammer_jarvis.research.models import ResearchContext, ResearchSource
from hammer_jarvis.research.orchestrator import ResearchOrchestrator


@dataclass
class EngineeringObjectReference:
    id: str
    type: str
    name: str
    source: str | None = None


@dataclass
class ResearchAnswer:
    answer: str
    sources: list[ResearchSource]
    engineering_objects: list[EngineeringObjectReference]
    recommendations: list[str]
    confidence: str
    generated_at: str


class ResearchLLM(Protocol):
    def generate(self, prompt: str) -> str:
        """Generate an answer from a prepared prompt without owning source retrieval."""


class MockResearchLLM:
    def generate(self, prompt: str) -> str:
        question = _extract_question(prompt)
        return (
            f"Deterministische Research-Antwort zu '{question}'. "
            "Diese Antwort basiert auf dem lokalen Research-Kontext und nutzt keine externen APIs."
        )


class AnswerEngine:
    def __init__(
        self,
        *,
        research_orchestrator: ResearchOrchestrator | None = None,
        llm: ResearchLLM | None = None,
    ) -> None:
        self.research_orchestrator = research_orchestrator or ResearchOrchestrator()
        self.llm = llm or MockResearchLLM()

    def build_answer(self, query: str) -> ResearchAnswer:
        context = self.research_orchestrator.build_context(_request(query))
        sources = context.sources
        if not sources:
            return ResearchAnswer(
                answer="Ich habe keine lokalen Quellen gefunden und erzeuge deshalb keine freie Research-Antwort.",
                sources=[],
                engineering_objects=[],
                recommendations=["Lokale Knowledge-Dokumente oder Engineering-Projektdaten hinzufügen."],
                confidence="niedrig",
                generated_at=_now(),
            )
        return ResearchAnswer(
            answer=self.llm.generate(context.prompt),
            sources=sources,
            engineering_objects=_engineering_objects(context),
            recommendations=_recommendations(context),
            confidence=_confidence(context),
            generated_at=_now(),
        )


def _request(query: str):
    from hammer_jarvis.research.models import ResearchRequest

    return ResearchRequest(query=query)


def _engineering_objects(context: ResearchContext) -> list[EngineeringObjectReference]:
    objects = []
    for source in context.sources:
        if source.type != "GRAPH":
            continue
        objects.append(
            EngineeringObjectReference(
                id=str(source.metadata.get("node_id") or source.id),
                type=str(source.metadata.get("node_type") or "EngineeringObject"),
                name=source.title,
                source=source.metadata.get("source_file"),
            )
        )
    return objects


def _recommendations(context: ResearchContext) -> list[str]:
    recommendations = []
    if _has_type(context.sources, "GRAPH"):
        recommendations.append("Engineering-Objekte im Graph prüfen.")
    if _has_type(context.sources, "KNOWLEDGE"):
        recommendations.append("Passende Knowledge-Quelle öffnen und Details gegenprüfen.")
    if _has_type(context.sources, "CAPABILITY"):
        recommendations.append("Verfügbare lokale Capability für den nächsten read-only Schritt nutzen.")
    if not recommendations:
        recommendations.append("Weitere lokale Quellen indexieren.")
    return recommendations


def _confidence(context: ResearchContext) -> str:
    source_count = int(context.statistics.get("source_count", len(context.sources)))
    if source_count >= 3 and _has_type(context.sources, "GRAPH"):
        return "hoch"
    if source_count >= 1:
        return "mittel"
    return "niedrig"


def _has_type(sources: list[ResearchSource], source_type: str) -> bool:
    return any(source.type == source_type for source in sources)


def _extract_question(prompt: str) -> str:
    marker = "Benutzerfrage"
    if marker not in prompt:
        return "unbekannte Frage"
    return prompt.split(marker, 1)[1].strip().splitlines()[0].strip() or "unbekannte Frage"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
