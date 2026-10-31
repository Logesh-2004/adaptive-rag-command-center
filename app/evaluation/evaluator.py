import re
from collections import OrderedDict
from hashlib import sha256
from typing import Any, Dict, List, Sequence, Union

from langchain_core.documents import Document

from app.core.config import Settings
from app.core.logger import append_jsonl, utc_timestamp

_EVALUATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_MAX_EVALUATION_CACHE = 128
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on",
    "or", "that", "the", "to", "with",
}


def _context_to_text(context: Sequence[Union[str, Document]]) -> str:
    if context and isinstance(context[0], Document):
        return "\n\n".join(doc.page_content for doc in context)  # type: ignore[union-attr]
    return "\n\n".join(str(item) for item in context)


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()) if token not in _STOPWORDS}


def _has_basic_contradiction(answer: str, context_text: str) -> bool:
    answer_text = f" {answer.lower()} "
    context_lower = f" {context_text.lower()} "
    if len(_tokens(answer) & _tokens(context_text)) < 3:
        return False

    contradiction_patterns = (
        (" is not ", " is "),
        (" are not ", " are "),
        (" does not ", " does "),
        (" do not ", " do "),
        (" cannot ", " can "),
        (" excludes ", " includes "),
        (" decreases ", " increases "),
        (" disabled ", " enabled "),
    )
    return any(negative in answer_text and positive in context_lower and negative not in context_lower for negative, positive in contradiction_patterns)


def _average_relevance(context: Sequence[Union[str, Document]]) -> float:
    scores = []
    for item in context:
        if isinstance(item, Document):
            score = item.metadata.get("relevance_score")
            if score is not None:
                scores.append(_clamp_score(score))
    return sum(scores) / len(scores) if scores else 0.5


def validate_grounding(
    query: str,
    context: Sequence[Union[str, Document]],
    answer: str,
    settings: Settings,
) -> Dict[str, Any]:
    """Estimate grounding from lexical overlap and simple contradiction patterns."""
    context_items = [doc.page_content if isinstance(doc, Document) else str(doc) for doc in context]
    context_text = "\n\n".join(context_items)
    if not answer.strip() or not context_text.strip():
        return {"grounding_score": 0.0, "grounding": 0.0, "grounded": False, "grounding_method": "token_overlap"}

    answer_tokens = _tokens(answer)
    context_tokens = _tokens(context_text)
    query_tokens = _tokens(query)
    answer_overlap = len(answer_tokens & context_tokens) / max(1, len(answer_tokens))
    query_context_overlap = len(query_tokens & context_tokens) / max(1, len(query_tokens))
    grounding_score = min(1.0, 0.75 * answer_overlap + 0.25 * query_context_overlap)
    contradiction = _has_basic_contradiction(answer, context_text)
    grounded = not contradiction and (
        answer_overlap >= settings.grounding_overlap_threshold
        or (answer_overlap >= 0.12 and query_context_overlap >= 0.5)
    )
    return {
        "grounding_score": round(float(grounding_score), 4),
        "grounding": round(float(grounding_score), 4),
        "grounded": grounded,
        "keyword_overlap": round(float(answer_overlap), 4),
        "contradiction_detected": contradiction,
        "grounding_method": "token_overlap",
    }


def _evaluation_cache_key(query: str, context_text: str, answer: str) -> str:
    return sha256(f"lexical-v1\n{query}\n{context_text}\n{answer}".encode("utf-8")).hexdigest()


def _remember_evaluation(key: str, evaluation: Dict[str, Any]) -> None:
    _EVALUATION_CACHE[key] = dict(evaluation)
    _EVALUATION_CACHE.move_to_end(key)
    while len(_EVALUATION_CACHE) > _MAX_EVALUATION_CACHE:
        _EVALUATION_CACHE.popitem(last=False)


def _risk_from_scores(grounding: Dict[str, Any], faithfulness: float, relevance: float, retrieval_confidence: float, settings: Settings) -> str:
    if grounding.get("contradiction_detected"):
        return "high"
    if faithfulness >= 0.45 and relevance >= 0.30 and retrieval_confidence >= settings.retrieval_confidence_threshold:
        return "low"
    if faithfulness >= 0.25 and relevance >= 0.20:
        return "medium"
    return "high"


def evaluate_answer(query: str, context: Sequence[Union[str, Document]], answer: str, settings: Settings) -> Dict[str, Any]:
    """Deterministically score answer grounding and relevance with lexical checks."""
    context_text = _context_to_text(context)
    key = _evaluation_cache_key(query, context_text, answer)
    cached = _EVALUATION_CACHE.get(key)
    if cached is not None:
        _EVALUATION_CACHE.move_to_end(key)
        return dict(cached)

    grounding = validate_grounding(query, context, answer, settings)
    unsupported_sentences = _unsupported_sentences(answer, context)
    retrieval_confidence = _average_relevance(context)
    query_tokens = _tokens(query)
    query_answer_overlap = len(query_tokens & _tokens(answer)) / max(1, len(query_tokens))
    query_context_overlap = len(query_tokens & _tokens(context_text)) / max(1, len(query_tokens))
    relevance = _clamp_score(0.45 * retrieval_confidence + 0.35 * query_answer_overlap + 0.20 * query_context_overlap)
    faithfulness = _clamp_score(0.72 * float(grounding["grounding_score"]) + 0.28 * retrieval_confidence)
    hallucination_risk = _risk_from_scores(grounding, faithfulness, relevance, retrieval_confidence, settings)
    evaluation = {
        **grounding,
        "faithfulness": round(faithfulness, 4),
        "relevance": round(relevance, 4),
        "answer_relevance": round(relevance, 4),
        "context_precision": round(retrieval_confidence, 4),
        "context_recall": round(max(query_context_overlap, grounding["keyword_overlap"]), 4),
        "hallucination_score": round(1.0 - faithfulness, 4),
        "lexical_grounding_score": grounding["grounding_score"],
        "retrieval_diversity_score": _diversity_score(context),
        "unsupported_sentences": unsupported_sentences,
        "repair_recommended": bool(unsupported_sentences) or hallucination_risk == "high",
        "retrieval_confidence": round(retrieval_confidence, 4),
        "hallucination_risk": hallucination_risk,
        "summary": (
            f"Lexical evaluation: grounding={grounding['grounding_score']:.2f}, "
            f"retrieval_confidence={retrieval_confidence:.2f}, risk={hallucination_risk}."
        ),
    }
    _remember_evaluation(key, evaluation)
    return evaluation


def _unsupported_sentences(answer: str, context: Sequence[Union[str, Document]]) -> list[str]:
    context_tokens = _tokens(_context_to_text(context))
    if not context_tokens:
        return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer) if sentence.strip()]
    unsupported = []
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        sentence = sentence.strip()
        if len(sentence.split()) < 5:
            continue
        sentence_tokens = _tokens(sentence)
        overlap = len(sentence_tokens & context_tokens) / max(1, len(sentence_tokens))
        if overlap < 0.12:
            unsupported.append(sentence)
    return unsupported[:3]


def _diversity_score(context: Sequence[Union[str, Document]]) -> float:
    items = [item.page_content if isinstance(item, Document) else str(item) for item in context]
    if len(items) <= 1:
        return 1.0 if items else 0.0
    token_sets = [_tokens(item) for item in items]
    distances = []
    for index, left in enumerate(token_sets):
        for right in token_sets[index + 1 :]:
            union = len(left | right)
            overlap = len(left & right) / union if union else 0.0
            distances.append(1.0 - overlap)
    return round(sum(distances) / len(distances), 4) if distances else 0.0


def judge_answer(query: str, context: Sequence[Union[str, Document]], answer: str, settings: Settings) -> Dict[str, Any]:
    return evaluate_answer(query, context, answer, settings)


def log_evaluation(query: str, documents: List[Document], answer: str, settings: Settings) -> Dict[str, Any]:
    evaluation = evaluate_answer(query, documents, answer, settings)
    payload = {
        "timestamp": utc_timestamp(),
        "query": query,
        "answer": answer,
        "context": [doc.page_content for doc in documents],
        "source_count": len(documents),
        "evaluation": evaluation,
    }

    append_jsonl(settings.processed_data_dir / "evaluations.jsonl", payload, settings.log_max_bytes)
    return evaluation
