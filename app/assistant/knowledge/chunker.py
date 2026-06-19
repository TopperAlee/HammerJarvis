from typing import Any


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[dict[str, Any]]:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return []
    chunk_size = max(1, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            boundary = cleaned.rfind(" ", start + 1, end)
            if boundary > start:
                end = boundary
        chunks.append({"chunk_index": index, "text": cleaned[start:end], "start": start, "end": end})
        if end >= len(cleaned):
            break
        start = end - overlap
        index += 1
    return chunks
