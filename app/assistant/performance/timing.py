import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from app.assistant.performance.metrics_store import metrics_store


@contextmanager
def time_operation(name: str, category: str) -> Iterator[None]:
    started = time.perf_counter()
    success = True
    error_category = ""
    try:
        yield
    except Exception as exc:
        success = False
        error_category = exc.__class__.__name__
        raise
    finally:
        metrics_store.add(
            {
                "operation": name,
                "category": category,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "success": success,
                "error_category": error_category,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
