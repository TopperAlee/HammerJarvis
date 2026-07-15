from typing import Any

from hammer_jarvis.intent.models import IntentResult


class IntentParser:
    def parse_text(self, text: str, source: str = "api", context: dict[str, Any] | None = None) -> IntentResult:
        normalized = " ".join(text.strip().lower().split())
        active_context = context or {}
        rules: list[tuple[list[str], str, str]] = [
            (["wo wird", "finde objekt", "engineering query"], "engineering.query", "Engineering-Query erkannt."),
            (["zeige beziehungen", "welche beziehungen"], "engineering.object.relationships", "Engineering-Beziehungsfrage erkannt."),
            (["welche diagnosen betreffen", "diagnosen betreffen", "diagnosen zu"], "engineering.object.diagnostics", "Engineering-Diagnosefrage erkannt."),
            (["zeige dokumente zum projekt", "welche dokumente", "dokumente zu"], "engineering.object.documents", "Engineering-Dokumentfrage erkannt."),
            (["zeige verwaiste objekte", "verwaiste objekte"], "engineering.object.orphans", "Engineering-Waisenobjekte erkannt."),
            (["diagnose starten", "projekt prÃ¼fen", "projekt pruefen", "engineering prÃ¼fen", "engineering pruefen", "finde fehler", "qualitÃ¤tsprÃ¼fung starten", "qualitaetspruefung starten"], "engineering.diagnostics.run", "Engineering-Diagnose erkannt."),
            (["git status"], "development.git.status", "Git-Status erkannt."),
            (["tests ausführen", "pytest"], "development.tests.run", "Testausführung erkannt."),
            (["analysiere protool", "csv analysieren"], "engineering.protool.analyze", "ProTool-Analyse erkannt."),
            (["panel preview", "panel vorschau"], "engineering.panel.preview", "Panel-Vorschau erkannt."),
            (["protool assistant", "protool"], "engineering.protool.open", "ProTool Assistant erkannt."),
            (["projekt öffnen", "öffne projekt", "oeffne projekt"], "engineering.project.open", "Projekt öffnen erkannt."),
            (["engineering öffnen", "engineering oeffnen", "engineering"], "engineering.workspace.open", "Engineering Workspace erkannt."),
            (["suche dokument", "knowledge", "wissen"], "knowledge.search", "Wissenssuche erkannt."),
            (["systemstatus", "status"], "assistant.status", "Systemstatus erkannt."),
            (["was kannst du", "hilfe"], "assistant.help", "Hilfe erkannt."),
        ]
        for phrases, intent, message in rules:
            if any(phrase in normalized for phrase in phrases):
                return IntentResult(
                    intent=intent,
                    confidence=0.9,
                    source=source,
                    arguments={"text": text},
                    context=active_context,
                    requires_confirmation=False,
                    risk="GREEN",
                    message=message,
                )
        return IntentResult(
            intent="unknown",
            confidence=0.0,
            source=source,
            arguments={"text": text},
            context=active_context,
            requires_confirmation=False,
            risk="GREEN",
            message="Ich konnte den Befehl nicht eindeutig einem bekannten Intent zuordnen.",
        )
