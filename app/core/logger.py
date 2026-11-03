import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings

debug_logger = logging.getLogger("app.rag")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, record: dict, max_bytes: int) -> None:
    """Append one JSON record, first rotating the file to <name>.1.jsonl once it reaches max_bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.stat().st_size >= max_bytes:
            os.replace(path, path.with_name(f"{path.stem}.1{path.suffix}"))
    except FileNotFoundError:
        pass
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def log_event(settings: Settings, event_type: str, payload: dict) -> None:
    """Append a JSONL event to the observability log file."""
    event = {
        "timestamp": utc_timestamp(),
        "event_type": event_type,
        **payload,
    }
    append_jsonl(settings.processed_data_dir / "system_logs.jsonl", event, settings.log_max_bytes)


def log_debug_event(settings: Settings, event_type: str, payload: dict) -> None:
    """Record full prompts and passages, only when RAG_DEBUG_LOGS is enabled."""
    if not settings.rag_debug_logs:
        return
    debug_logger.debug("%s %s", event_type, json.dumps(payload, ensure_ascii=False, default=str))
    log_event(settings, event_type, payload)
