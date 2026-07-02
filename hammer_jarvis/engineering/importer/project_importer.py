from dataclasses import dataclass

from hammer_jarvis.engineering.classifier.protool import ProjectFileType, ProToolClassifier
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphEdge, GraphNode
from hammer_jarvis.engineering.models import Project, ProjectFile
from hammer_jarvis.engineering.scanner.filesystem import ProjectScanResult
from hammer_jarvis.engineering.importer.protool_importer import ProToolImporter


@dataclass
class ImportedProject:
    project: Project
    graph: EngineeringGraph


class ProjectImporter:
    def __init__(self, classifier: ProToolClassifier | None = None) -> None:
        self.classifier = classifier or ProToolClassifier()

    def import_scan(
        self,
        scan_result: ProjectScanResult,
        *,
        import_protool_texts: bool = False,
        panel: str = "OP7",
        text_column: int = 2,
        encoding: str = "cp1252",
    ) -> ImportedProject:
        project_id = _project_id(scan_result.root_path.name)
        project_node = GraphNode(
            id=f"project:{project_id}",
            type="Project",
            name=scan_result.root_path.name,
            source_file=str(scan_result.root_path),
            metadata={"root_path": str(scan_result.root_path)},
        )
        project_files: list[ProjectFile] = []
        nodes = [project_node]
        edges: list[GraphEdge] = []

        for scanned_file in sorted(scan_result.files, key=lambda item: item.relative_path.lower()):
            file_type = self.classifier.classify(scanned_file.path)
            module = "protool" if file_type is not ProjectFileType.UNKNOWN else None
            project_file = ProjectFile(
                name=scanned_file.path.name,
                path=str(scanned_file.path),
                kind=file_type.value,
                module=module,
            )
            project_files.append(project_file)
            file_node = GraphNode(
                id=f"file:{project_id}:{scanned_file.relative_path}",
                type="ProjectFile",
                name=scanned_file.path.name,
                source_file=str(scanned_file.path),
                metadata={
                    "relative_path": scanned_file.relative_path,
                    "kind": file_type.value,
                    "module": module,
                },
            )
            nodes.append(file_node)
            edges.append(
                GraphEdge(
                    source_id=project_node.id,
                    target_id=file_node.id,
                    type="CONTAINS",
                    metadata={"source": "project_importer"},
                )
            )
            if import_protool_texts and module == "protool" and file_type in _PROTOOL_TEXT_FILE_TYPES:
                imported_texts = ProToolImporter().import_project_file(
                    project_file,
                    panel=panel,
                    text_column=text_column,
                    encoding=encoding,
                    project_file_node_id=file_node.id,
                )
                for node in imported_texts["graph"].nodes:
                    if node.id != file_node.id:
                        nodes.append(node)
                edges.extend(imported_texts["graph"].edges)

        return ImportedProject(
            project=Project(id=project_id, name=scan_result.root_path.name, files=project_files),
            graph=EngineeringGraph(nodes=nodes, edges=edges),
        )


def _project_id(name: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in name)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "engineering-project"


_PROTOOL_TEXT_FILE_TYPES = {
    ProjectFileType.MESSAGE_TEXT,
    ProjectFileType.ALARM_TEXT,
    ProjectFileType.INFO_TEXT,
    ProjectFileType.TEXT_LIST,
    ProjectFileType.RECIPE,
}
