from typing import Any


def format_memory_list(result: dict[str, Any]) -> str:
    memories = result.get("memories", [])
    if not memories:
        return "Ich habe dazu nichts im lokalen Gedächtnis gefunden."
    lines = [f"Ich habe {len(memories)} passende Erinnerung(en) gefunden:"]
    for item in memories[:10]:
        lines.append(f"- {item.get('key')}: {item.get('value')} ({item.get('type')})")
    return "\n".join(lines)


def format_memory_added(item: dict[str, Any]) -> str:
    return f"Ich habe das lokal gespeichert: {item.get('key')}: {item.get('value')}"
