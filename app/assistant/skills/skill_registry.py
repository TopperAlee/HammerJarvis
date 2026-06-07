from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.skills.document_skills import DocumentSummarySkill, KeyFieldExtractionSkill
from app.assistant.skills.report_skills import (
    DocumentIndexExcelSkill,
    FileSearchReportSkill,
    WebResearchExcelSkill,
    WebResearchReportSkill,
)
from app.assistant.tool_registry import ToolRegistry


class SkillRegistry:
    """Registry for high-level assistant skills composed from safe local tools."""

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self._skills = {
            skill.name: skill
            for skill in (
                DocumentSummarySkill(self.tool_registry),
                KeyFieldExtractionSkill(self.tool_registry),
                FileSearchReportSkill(self.tool_registry),
                WebResearchReportSkill(self.tool_registry),
                WebResearchExcelSkill(self.tool_registry),
                DocumentIndexExcelSkill(self.tool_registry),
            )
        }

    def list_skills(self) -> dict[str, Any]:
        """Return public skill metadata without exposing implementation details."""
        return {
            "skills": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "risk": skill.risk,
                    "required_tools": skill.required_tools,
                }
                for skill in self._skills.values()
            ]
        }

    def execute(self, name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a registered skill; unknown skill names are rejected safely."""
        if name not in self._skills:
            return {
                "skill": name,
                "risk": ActionRisk.GREEN,
                "error": True,
                "message": "Skill ist nicht registriert.",
            }
        return self._skills[name].execute(input_data or {})
