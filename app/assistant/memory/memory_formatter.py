from typing import Any


def format_memory_list(result: dict[str, Any]) -> str:
    memories = result.get("memories", [])
    if not memories:
        return "Ich habe keine passende Erinnerung gefunden."
    if len(memories) == 1:
        return f"Ich weiß: {_memory_sentence(memories[0])}."
    lines = [f"Ich habe {len(memories)} passende Erinnerungen gefunden:"]
    for item in memories[:10]:
        lines.append(f"- {_memory_sentence(item)}.")
    return "\n".join(lines)


def format_memory_added(item: dict[str, Any]) -> str:
    prefix = "Erinnerung aktualisiert" if item.get("updated") else "Gemerkte Information"
    return f"{prefix}: {_memory_sentence(item)}."


def _memory_sentence(item: dict[str, Any]) -> str:
    key = str(item.get("key") or "Erinnerung").strip()
    value = str(item.get("value") or "").strip()
    if item.get("type") in {"device", "alias"}:
        return f"{key} ist das {value}".strip()
    return f"{key}: {value}".strip()
