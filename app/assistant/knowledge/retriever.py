from app.assistant.knowledge.knowledge_store import KnowledgeStore


def search_knowledge(query: str, limit: int = 8) -> dict:
    return KnowledgeStore().search_knowledge(query, limit=limit)
