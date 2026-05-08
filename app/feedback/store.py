import json
from datetime import datetime
from app.core.config import Settings
from app.api.schemas import FeedbackRequest


def store_feedback(request: FeedbackRequest, settings: Settings) -> None:
    """Persist user feedback for the adaptive RAG pipeline."""
    settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = settings.processed_data_dir / "feedback.jsonl"

    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "query": request.query,
        "answer": request.answer,
        "rating": request.rating,
        "comment": request.comment,
    }

    with feedback_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
