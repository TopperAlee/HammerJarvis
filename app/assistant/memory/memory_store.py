import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.assistant.memory.memory_classifier import normalize_relation_value
from app.assistant.memory.memory_models import build_memory_item
from app.logging_utils.audit import write_audit_log


class MemoryStore:
    """Small UTF-8 JSON memory store for explicit, user-approved memories."""

    def __init__(self) -> None:
        self.path = Path(os.getenv("MEMORY_FILE", "app/data/memory/memory.json"))
        self.max_items = _int_env("MEMORY_MAX_ITEMS", 1000)

    def add_memory(self, item: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        memory = build_memory_item(item)
        existing = self._find_updatable_memory(data["memories"], memory)
        if existing is not None:
            existing["value"] = memory.get("value", "")
            existing["tags"] = _merge_tags(existing.get("tags", []), memory.get("tags", []))
            existing["source"] = memory.get("source", existing.get("source", "user"))
            existing["confidence"] = memory.get("confidence", existing.get("confidence", "high"))
            existing["source_text"] = memory.get("source_text", existing.get("source_text", ""))
            existing["updated_at"] = _now()
            self._save(data)
            existing["updated"] = True
            write_audit_log("memory_update", {"id": existing["id"], "type": existing["type"], "key": existing["key"]})
            return existing
        data["memories"] = [*data["memories"], memory][-self.max_items :]
        self._save(data)
        write_audit_log("memory_add", {"id": memory["id"], "type": memory["type"], "key": memory["key"]})
        return memory

    def update_memory(self, memory_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        for item in data["memories"]:
            if item["id"] == memory_id:
                item.update({key: value for key, value in patch.items() if key not in {"id", "created_at"}})
                item["updated_at"] = _now()
                self._save(data)
                write_audit_log("memory_update", {"id": memory_id})
                return item
        return {"error": True, "message": "Memory nicht gefunden."}

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        data = self._load()
        before = len(data["memories"])
        data["memories"] = [item for item in data["memories"] if item.get("id") != memory_id]
        deleted = len(data["memories"]) != before
        self._save(data)
        write_audit_log("memory_delete", {"id": memory_id, "deleted": deleted})
        return {"deleted": deleted, "id": memory_id}

    def search_memory(
        self,
        query: str,
        tags: list[str] | None = None,
        type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        needle = str(query).lower()
        tag_set = {tag.lower() for tag in tags or []}
        matches = []
        for item in self._load()["memories"]:
            haystack = f"{item.get('key', '')} {item.get('value', '')} {' '.join(item.get('tags', []))}".lower()
            if type and item.get("type") != type:
                continue
            if tag_set and not tag_set.intersection({str(tag).lower() for tag in item.get("tags", [])}):
                continue
            if needle in haystack:
                item["last_used_at"] = _now()
                matches.append(item)
        if matches:
            self._save(self._load() | {"memories": self._merge_used(matches)})
        return {"query": query, "count": len(matches), "memories": matches[:limit]}

    def list_memory(self, type: str | None = None, tag: str | None = None, limit: int = 100) -> dict[str, Any]:
        items = self._load()["memories"]
        if type:
            items = [item for item in items if item.get("type") == type]
        if tag:
            items = [item for item in items if tag in item.get("tags", [])]
        return {"count": len(items), "memories": items[-limit:]}

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        for item in self._load()["memories"]:
            if item.get("id") == memory_id:
                return item
        return {"error": True, "message": "Memory nicht gefunden."}

    def export_memory(self) -> dict[str, Any]:
        return self._load()

    def import_memory(self, data: dict[str, Any]) -> dict[str, Any]:
        memories = data.get("memories", []) if isinstance(data, dict) else []
        self._save({"memories": [build_memory_item(item) for item in memories if isinstance(item, dict)]})
        return self.export_memory()

    def repair_memory_values(self, dry_run: bool = True) -> dict[str, Any]:
        data = self._load()
        changes = []
        for item in data["memories"]:
            if item.get("type") not in {"device", "alias"}:
                continue
            old_value = str(item.get("value", ""))
            new_value = normalize_relation_value(old_value)
            if not new_value or new_value == old_value or not _looks_like_malformed_relation_value(old_value):
                continue
            change = {
                "id": item.get("id"),
                "key": item.get("key"),
                "old_value": old_value,
                "new_value": new_value,
            }
            changes.append(change)
            if not dry_run:
                item["value"] = new_value
                item["updated_at"] = _now()
        if changes and not dry_run:
            self._save(data)
            write_audit_log("memory_repair", {"repairable": len(changes), "applied": True})
        return {
            "dry_run": dry_run,
            "examined": len(data["memories"]),
            "repairable": len(changes),
            "changes": changes,
        }

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {"memories": []}
        return {"memories": data.get("memories", []) if isinstance(data, dict) and isinstance(data.get("memories"), list) else []}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _merge_used(self, used_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item["id"]: item for item in used_items}
        return [by_id.get(item["id"], item) for item in self._load()["memories"]]

    def _find_updatable_memory(self, memories: list[dict[str, Any]], memory: dict[str, Any]) -> dict[str, Any] | None:
        if memory.get("type") not in {"device", "alias"}:
            return None
        key = str(memory.get("key", "")).strip().lower()
        if not key:
            return None
        for item in memories:
            if item.get("type") in {"device", "alias"} and str(item.get("key", "")).strip().lower() == key:
                return item
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _merge_tags(existing: list[Any], incoming: list[Any]) -> list[str]:
    merged: list[str] = []
    for tag in [*existing, *incoming]:
        tag_text = str(tag).strip()
        if tag_text and tag_text not in merged:
            merged.append(tag_text)
    return merged


def _looks_like_malformed_relation_value(value: str) -> bool:
    return bool(re.search(r"\s+(ist|bedeutet|heißt|heisst)\s*$", value.strip(), re.I))
