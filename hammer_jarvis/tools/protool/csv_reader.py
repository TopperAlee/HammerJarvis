import csv
from pathlib import Path
from typing import Any


SUPPORTED_DELIMITERS = (";", ",", "\t")


def read_protool_csv(file_path: str | Path, encoding: str = "cp1252") -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    if not path.is_file():
        raise ValueError(f"CSV path is not a file: {path}")

    try:
        with path.open("r", encoding=encoding, newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            delimiter = _detect_delimiter(sample)
            reader = csv.reader(handle, delimiter=delimiter)
            rows = [row for row in reader]
    except LookupError as exc:
        raise ValueError(f"Unsupported encoding: {encoding}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"CSV file cannot be decoded with encoding '{encoding}'.") from exc
    except csv.Error as exc:
        raise ValueError(f"CSV file cannot be parsed: {exc}") from exc

    return {"rows": rows, "delimiter": delimiter, "encoding": encoding}


def _detect_delimiter(sample: str) -> str:
    if not sample:
        return ";"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(SUPPORTED_DELIMITERS))
        if dialect.delimiter in SUPPORTED_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass

    counts = {delimiter: sample.count(delimiter) for delimiter in SUPPORTED_DELIMITERS}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ";"
