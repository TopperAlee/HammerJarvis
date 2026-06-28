from dataclasses import dataclass, field


@dataclass
class ProjectFile:
    name: str
    path: str | None = None
    kind: str = "unknown"
    module: str | None = None


@dataclass
class Variable:
    name: str
    data_type: str = ""
    address: str | None = None
    comment: str = ""


@dataclass
class TextResource:
    key: str
    text: str
    language: str = ""
    source_file: str | None = None


@dataclass
class Alarm:
    id: str
    text: str
    severity: str = ""
    source_file: str | None = None


@dataclass
class Recipe:
    name: str
    fields: list[str] = field(default_factory=list)
    source_file: str | None = None


@dataclass
class ProgramBlock:
    name: str
    block_type: str = ""
    number: str | None = None
    source_file: str | None = None


@dataclass
class Reference:
    source: str
    target: str
    relation: str = ""
    context: str = ""


@dataclass
class Project:
    id: str
    name: str
    files: list[ProjectFile] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    text_resources: list[TextResource] = field(default_factory=list)
    alarms: list[Alarm] = field(default_factory=list)
    recipes: list[Recipe] = field(default_factory=list)
    program_blocks: list[ProgramBlock] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)

