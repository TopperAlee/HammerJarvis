COMMANDS: list[dict[str, object]] = [
    {
        "intent": "engineering.workspace.open",
        "label": "Engineering öffnen",
        "examples": ["engineering", "engineering öffnen"],
    },
    {
        "intent": "engineering.project.open",
        "label": "Projekt öffnen",
        "examples": ["projekt öffnen", "öffne projekt Retro Presse"],
    },
    {
        "intent": "engineering.protool.open",
        "label": "ProTool Assistant öffnen",
        "examples": ["protool", "protool assistant"],
    },
    {
        "intent": "engineering.protool.analyze",
        "label": "ProTool CSV analysieren",
        "examples": ["analysiere protool", "csv analysieren"],
    },
    {
        "intent": "engineering.panel.preview",
        "label": "Panel-Vorschau öffnen",
        "examples": ["panel preview", "panel vorschau"],
    },
    {
        "intent": "engineering.diagnostics.run",
        "label": "Engineering-Diagnose starten",
        "examples": ["diagnose starten", "projekt pruefen", "finde fehler"],
    },
    {
        "intent": "engineering.query",
        "label": "Engineering Copilot fragen",
        "examples": ["Wo wird Hydraulik verwendet?", "Zeige verwaiste Objekte", "Welche Diagnosen betreffen diese Datei?"],
    },
    {
        "intent": "engineering.object.relationships",
        "label": "Engineering-Beziehungen anzeigen",
        "examples": ["zeige Beziehungen", "welche Beziehungen hat Hydraulik"],
    },
    {
        "intent": "engineering.object.diagnostics",
        "label": "Engineering-Diagnosen anzeigen",
        "examples": ["welche Diagnosen betreffen diese Datei", "Diagnosen zu Hydraulik"],
    },
    {
        "intent": "engineering.object.documents",
        "label": "Engineering-Dokumente anzeigen",
        "examples": ["zeige Dokumente zum Projekt", "Dokumente zu MessageText"],
    },
    {
        "intent": "engineering.object.orphans",
        "label": "Verwaiste Objekte anzeigen",
        "examples": ["zeige verwaiste Objekte"],
    },
    {
        "intent": "knowledge.search",
        "label": "Wissen suchen",
        "examples": ["knowledge", "suche dokument Hydraulik"],
    },
    {
        "intent": "assistant.status",
        "label": "Systemstatus anzeigen",
        "examples": ["status", "systemstatus"],
    },
    {
        "intent": "assistant.help",
        "label": "Hilfe anzeigen",
        "examples": ["hilfe", "was kannst du"],
    },
    {
        "intent": "development.git.status",
        "label": "Git Status anzeigen",
        "examples": ["git status"],
    },
    {
        "intent": "development.tests.run",
        "label": "Tests ausführen",
        "examples": ["tests ausführen", "pytest"],
    },
]


def get_commands() -> list[dict[str, object]]:
    return [command.copy() for command in COMMANDS]
