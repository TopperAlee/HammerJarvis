from typing import Any

from hammer_jarvis.engineering.models import Project


class EngineeringTreeBuilder:
    def build(self, project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "type": "Project",
            "name": project.name,
            "children": [
                {
                    "id": f"{project.id}:{project_file.name}",
                    "type": "ProjectFile",
                    "name": project_file.name,
                    "kind": project_file.kind,
                    "module": project_file.module,
                    "path": project_file.path,
                    "children": [],
                }
                for project_file in project.files
            ],
        }

