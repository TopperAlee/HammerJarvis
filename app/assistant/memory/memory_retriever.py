import os

from app.assistant.memory.memory_store import MemoryStore


def relevant_memory_context(message: str, limit: int | None = None) -> str:
    limit = limit or int(os.getenv("LLM_MAX_PROMPT_MEMORY_ITEMS", "8"))
    result = MemoryStore().search_memory(message, limit=limit)
    memories = result.get("memories", [])
    if not memories:
        # Fall back to token overlap for short user questions.
        tokens = [token for token in message.replace("?", " ").split() if len(token) > 3]
        collected = []
        for token in tokens:
            for item in MemoryStore().search_memory(token, limit=limit).get("memories", []):
                if item not in collected:
                    collected.append(item)
        memories = collected[:limit]
    if not memories:
        return ""
    lines = ["Lokaler Memory-Kontext:"]
    for item in memories[:limit]:
        lines.append(f"- {item.get('type')}: {item.get('key')} = {item.get('value')}")
    return "\n".join(lines)[: int(os.getenv("LLM_MAX_CONTEXT_CHARS", "12000"))]
