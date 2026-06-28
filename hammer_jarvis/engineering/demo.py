from dataclasses import asdict
from typing import Any

from hammer_jarvis.engineering.models import Project, ProjectFile


def get_demo_projects() -> list[dict[str, Any]]:
    project = Project(
        id="demo-project",
        name="Beispielprojekt",
        files=[
            ProjectFile(name="MessageText.csv", kind="hmi_text", module="protool"),
            ProjectFile(name="AlarmText.csv", kind="alarm_text", module="protool"),
            ProjectFile(name="Variables.csv", kind="variables", module="protool"),
            ProjectFile(name="HelpText.csv", kind="help_text", module="protool"),
            ProjectFile(name="Recipes.csv", kind="recipes", module="protool"),
        ],
    )
    return [asdict(project)]

