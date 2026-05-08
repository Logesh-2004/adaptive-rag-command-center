import json
from datetime import datetime
from app.core.config import Settings


def log_event(settings: Settings, event_type: str, payload: dict) -> None:
    """Append a JSONL event to the observability log file."""
    settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.processed_data_dir / "system_logs.jsonl"
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
