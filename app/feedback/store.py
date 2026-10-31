from app.core.config import Settings
from app.core.logger import append_jsonl, utc_timestamp
from app.api.schemas import FeedbackRequest


def store_feedback(request: FeedbackRequest, settings: Settings) -> None:
    """Persist user feedback for the adaptive RAG pipeline."""
    payload = {
        "timestamp": utc_timestamp(),
        "query": request.query,
        "answer": request.answer,
        "rating": request.rating,
        "comment": request.comment,
    }
    append_jsonl(settings.processed_data_dir / "feedback.jsonl", payload, settings.log_max_bytes)
