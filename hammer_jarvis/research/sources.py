from __future__ import annotations


def available_research_sources() -> list[dict[str, object]]:
    return [
        {
            "id": "GRAPH",
            "type": "GRAPH",
            "title": "Engineering Graph",
            "enabled": True,
            "local_only": True,
        },
        {
            "id": "KNOWLEDGE",
            "type": "KNOWLEDGE",
            "title": "Knowledge Store",
            "enabled": True,
            "local_only": True,
        },
        {
            "id": "CAPABILITY",
            "type": "CAPABILITY",
            "title": "Capability Registry",
            "enabled": True,
            "local_only": True,
        },
        {
            "id": "DOCUMENT",
            "type": "DOCUMENT",
            "title": "Indexed Documents",
            "enabled": True,
            "local_only": True,
        },
        {
            "id": "WEB",
            "type": "WEB",
            "title": "Web Research",
            "enabled": False,
            "local_only": False,
        },
    ]
