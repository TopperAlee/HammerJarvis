from enum import StrEnum
from pathlib import Path


class ProjectFileType(StrEnum):
    UNKNOWN = "UNKNOWN"
    MESSAGE_TEXT = "MESSAGE_TEXT"
    ALARM_TEXT = "ALARM_TEXT"
    INFO_TEXT = "INFO_TEXT"
    TEXT_LIST = "TEXT_LIST"
    RECIPE = "RECIPE"
    VARIABLES = "VARIABLES"


class ProToolClassifier:
    _KNOWN_FILES = {
        "messagetext.csv": ProjectFileType.MESSAGE_TEXT,
        "alarmtext.csv": ProjectFileType.ALARM_TEXT,
        "infohelptext.csv": ProjectFileType.INFO_TEXT,
        "textlist.csv": ProjectFileType.TEXT_LIST,
        "recipetext.csv": ProjectFileType.RECIPE,
        "variables.csv": ProjectFileType.VARIABLES,
    }

    def classify(self, file_name: str | Path) -> ProjectFileType:
        return self._KNOWN_FILES.get(Path(file_name).name.lower(), ProjectFileType.UNKNOWN)

