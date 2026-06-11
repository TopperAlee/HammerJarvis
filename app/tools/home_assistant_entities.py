import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.assistant.performance.timing import time_operation
from app.config.home_assistant_action_allowlist import get_allowed_actions
from app.config.settings import get_settings


ACTIONABLE_DOMAINS = {"light", "switch", "scene"}
BLOCKED_DOMAINS = {
    "lock",
    "alarm_control_panel",
    "cover",
    "climate",
    "fan",
    "valve",
    "siren",
    "camera",
}
SWITCH_WARNING = "Switches können auch Steckdosen oder Geräte sein. Nur freigeben, wenn sicher."


_SYNC_LOCKS: dict[str, threading.Lock] = {}
_LAST_LIVE_SYNC: dict[str, float] = {}
_SYNC_LOCKS_GUARD = threading.Lock()


class HomeAssistantEntityCatalog:
    """Read-only Home Assistant entity catalog.

    The catalog intentionally stores only a small safe metadata subset. Entity
    discovery is GREEN/read-only and never grants control rights; switching still
    requires safe domain validation, explicit allowlist membership and YELLOW
    confirmation in the separate action layer.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self.cache_file = Path(os.getenv("HA_ENTITY_CACHE_FILE", "app/data/home_assistant/entities_cache.json"))
        self.max_age_seconds = _int_env("HA_ENTITY_CACHE_MAX_AGE_SECONDS", 900)

    def fetch_all_entities(self) -> dict[str, Any]:
        settings = self._settings.require_home_assistant()
        assert settings.home_assistant_url is not None
        assert settings.home_assistant_token is not None
        url = f"{settings.home_assistant_url.rstrip('/')}/api/states"
        with time_operation("home_assistant_entities.fetch_all", "home_assistant"):
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {settings.home_assistant_token}"},
                timeout=float(os.getenv("HOME_ASSISTANT_TIMEOUT_SECONDS", "10")),
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Home Assistant states response must be a list")
        entities = [self._safe_entity(item) for item in payload if isinstance(item, dict)]
        return {
            "provider": "home_assistant",
            "source": "live",
            "entity_count": len(entities),
            "entities": entities,
            "last_sync": _now_iso(),
        }

    def save_cache(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "provider": "home_assistant",
            "source": "cache",
            "last_sync": _now_iso(),
            "entity_count": len(entities),
            "entities": entities,
        }
        self.cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return data

    def load_cache(self) -> dict[str, Any]:
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {
                "provider": "home_assistant",
                "source": "none",
                "entity_count": 0,
                "entities": [],
                "cache_file_exists": False,
            }
        entities = data.get("entities") if isinstance(data, dict) else []
        if not isinstance(entities, list):
            entities = []
        return {
            "provider": "home_assistant",
            "source": "cache",
            "last_sync": data.get("last_sync") if isinstance(data, dict) else None,
            "entity_count": len(entities),
            "entities": entities,
            "cache_file_exists": self.cache_file.exists(),
            "cache_age_seconds": self._cache_age_seconds(),
        }

    def sync_entities(self, force: bool = False) -> dict[str, Any]:
        cache_key = str(self.cache_file.resolve())
        lock = _sync_lock_for(cache_key)
        with time_operation("home_assistant_entities.sync", "home_assistant"):
            with lock:
                cached = self.load_cache()
                if not force and self._cache_is_fresh(cached):
                    return {**cached, "source": "cache"}
                if not force and self._recent_live_sync(cache_key):
                    recent_cache = self.load_cache()
                    if recent_cache.get("entity_count", 0) > 0:
                        return {**recent_cache, "source": "cache_recent_live_sync"}
                try:
                    live = self.fetch_all_entities()
                    self.save_cache(live["entities"])
                    _LAST_LIVE_SYNC[cache_key] = time.monotonic()
                    return live
                except Exception:
                    if cached.get("entity_count", 0) > 0:
                        return {
                            **cached,
                            "source": "cache",
                            "warning": "Home Assistant nicht erreichbar. Ich nutze den letzten lokalen Entity-Cache.",
                        }
                    return {
                        "provider": "home_assistant",
                        "source": "none",
                        "error": True,
                        "entity_count": 0,
                        "entities": [],
                        "message": "Home Assistant ist nicht erreichbar und es gibt keinen lokalen Entity-Cache.",
                    }

    def list_entities(
        self,
        domain: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        data = self.sync_entities(force=False)
        entities = list(data.get("entities") or [])
        if domain:
            entities = [item for item in entities if item.get("domain") == domain]
        if state:
            entities = [item for item in entities if str(item.get("state", "")).lower() == state.lower()]
        limited = entities[: max(0, limit)]
        return {
            "provider": "home_assistant",
            "source": data.get("source"),
            "domain": domain,
            "count": len(entities),
            "entities": limited,
            "message": f"Ich habe {len(entities)} Home-Assistant-Entities gefunden.",
        }

    def search_entities(
        self,
        query: str,
        domain: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        needle = query.strip().lower()
        data = self.sync_entities(force=False)
        matches = []
        for entity in data.get("entities") or []:
            if domain and entity.get("domain") != domain:
                continue
            searchable = f"{entity.get('entity_id', '')} {entity.get('friendly_name', '')}".lower()
            if needle in searchable:
                matches.append(entity)
        return {
            "provider": "home_assistant",
            "source": data.get("source"),
            "query": query,
            "count": len(matches),
            "entities": matches[: max(0, limit)],
            "message": f"Ich habe {len(matches)} Home-Assistant-Entities gefunden.",
        }

    def list_unavailable_entities(self, limit: int = 100) -> dict[str, Any]:
        data = self.sync_entities(force=False)
        unavailable = [item for item in data.get("entities") or [] if item.get("is_unavailable")]
        return {
            "provider": "home_assistant",
            "source": data.get("source"),
            "count": len(unavailable),
            "entities": unavailable[: max(0, limit)],
            "message": f"Ich habe {len(unavailable)} unavailable Entities gefunden.",
        }

    def list_actionable_candidates(self, limit: int = 100) -> dict[str, Any]:
        data = self.sync_entities(force=False)
        candidates = [item for item in data.get("entities") or [] if item.get("is_actionable_candidate")]
        for item in candidates:
            if item.get("domain") == "switch":
                item.setdefault("warning", SWITCH_WARNING)
        order = {"light": 0, "scene": 1, "switch": 2}
        candidates.sort(key=lambda item: (order.get(str(item.get("domain")), 99), str(item.get("friendly_name") or item.get("entity_id"))))
        return {
            "provider": "home_assistant",
            "source": data.get("source"),
            "count": len(candidates),
            "entities": candidates[: max(0, limit)],
            "message": f"Ich habe {len(candidates)} potenziell freigebbare Kandidaten gefunden.",
        }

    def get_entity(self, entity_id: str) -> dict[str, Any]:
        data = self.sync_entities(force=False)
        normalized = entity_id.strip().lower()
        for entity in data.get("entities") or []:
            if str(entity.get("entity_id", "")).lower() == normalized:
                return {"provider": "home_assistant", "source": data.get("source"), "found": True, "entity": entity}
        return {
            "provider": "home_assistant",
            "source": data.get("source"),
            "found": False,
            "entity_id": entity_id,
            "message": f"Ich habe {entity_id} im lokalen Entity-Katalog nicht gefunden.",
        }

    def status(self) -> dict[str, Any]:
        cached = self.load_cache()
        return {
            "enabled": os.getenv("HA_ENTITY_SYNC_ENABLED", "true").strip().lower() == "true",
            "cache_file_exists": self.cache_file.exists(),
            "cache_age_seconds": self._cache_age_seconds(),
            "entity_count": cached.get("entity_count", 0),
            "last_sync": cached.get("last_sync"),
            "source": cached.get("source", "none") if cached.get("entity_count", 0) else "none",
            "cache_file": str(self.cache_file),
        }

    def _safe_entity(self, item: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(item.get("entity_id", ""))
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
        state = str(item.get("state", ""))
        attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        allowlisted = _allowlist_entry(entity_id)
        candidate = domain in ACTIONABLE_DOMAINS and domain not in BLOCKED_DOMAINS
        result = {
            "entity_id": entity_id,
            "domain": domain,
            "state": state,
            "friendly_name": attributes.get("friendly_name"),
            "last_changed": item.get("last_changed"),
            "last_updated": item.get("last_updated"),
            "attributes_summary": {
                "device_class": attributes.get("device_class"),
                "unit_of_measurement": attributes.get("unit_of_measurement"),
                "icon": attributes.get("icon"),
            },
            "is_unavailable": state.lower() == "unavailable",
            "is_unknown": state.lower() == "unknown",
            "is_actionable_candidate": candidate,
            "is_allowlisted": allowlisted is not None,
        }
        if allowlisted:
            result["allowed_actions"] = allowlisted.get("allowed_actions", [])
        if domain == "climate":
            result["attributes_summary"].update(
                {
                    "current_temperature": attributes.get("current_temperature"),
                    "temperature": attributes.get("temperature"),
                    "target_temperature": attributes.get("target_temperature"),
                    "hvac_mode": attributes.get("hvac_mode"),
                }
            )
            result["current_temperature"] = attributes.get("current_temperature")
            result["temperature"] = attributes.get("temperature")
            result["target_temperature"] = attributes.get("target_temperature")
            result["hvac_mode"] = attributes.get("hvac_mode")
        if domain == "switch" and candidate:
            result["warning"] = SWITCH_WARNING
        return result

    def _cache_age_seconds(self) -> int | None:
        try:
            return max(0, int(time.time() - self.cache_file.stat().st_mtime))
        except OSError:
            return None

    def _cache_is_fresh(self, cached: dict[str, Any]) -> bool:
        age = cached.get("cache_age_seconds")
        return (
            cached.get("entity_count", 0) > 0
            and isinstance(age, (int, float))
            and age < self.max_age_seconds
        )

    def _recent_live_sync(self, cache_key: str) -> bool:
        min_interval = _int_env("HA_ENTITY_SYNC_MIN_INTERVAL_SECONDS", 30)
        last_sync = _LAST_LIVE_SYNC.get(cache_key)
        return min_interval > 0 and last_sync is not None and (time.monotonic() - last_sync) < min_interval


def _allowlist_entry(entity_id: str) -> dict[str, Any] | None:
    normalized = entity_id.lower()
    actions = get_allowed_actions()
    for entity in actions.get("allowed_entities", []):
        if isinstance(entity, dict) and str(entity.get("entity_id", "")).lower() == normalized:
            return entity
    for scene in actions.get("allowed_scenes", []):
        if isinstance(scene, dict) and str(scene.get("entity_id", "")).lower() == normalized:
            return scene
        if isinstance(scene, str) and scene.lower() == normalized:
            return {"entity_id": scene, "allowed_actions": ["turn_on"]}
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _sync_lock_for(cache_key: str) -> threading.Lock:
    with _SYNC_LOCKS_GUARD:
        lock = _SYNC_LOCKS.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _SYNC_LOCKS[cache_key] = lock
        return lock
