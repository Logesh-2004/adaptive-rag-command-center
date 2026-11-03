from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
import re
from time import perf_counter
from typing import Any, List, Tuple

from langchain_core.documents import Document

from app.core.config import Settings
from app.retrieval.hybrid import feedback_terms, keyword_search, reciprocal_rank_fusion
from app.retrieval.query_classifier import QueryPlan, classify_query, load_query_expansions
from app.retrieval.text import STOPWORDS, normalize_phrase_text, tokenize

_RETRIEVAL_CACHE: OrderedDict[tuple[str, int, str, str], Any] = OrderedDict()
_MAX_RETRIEVAL_CACHE = 64


def _cache_key(query: str, settings: Settings, k: int, mode: str) -> tuple[str, int, str, str]:
    return (query.strip().lower(), k, str(settings.lexical_index_path), mode)


def _remember_retrieval(key: tuple[str, int, str, str], value: Any) -> None:
    _RETRIEVAL_CACHE[key] = deepcopy(value)
    _RETRIEVAL_CACHE.move_to_end(key)
    while len(_RETRIEVAL_CACHE) > _MAX_RETRIEVAL_CACHE:
        _RETRIEVAL_CACHE.popitem(last=False)


def _cached_retrieval(key: tuple[str, int, str, str]) -> Any:
    cached = _RETRIEVAL_CACHE.get(key)
    if cached is None:
        return None
    _RETRIEVAL_CACHE.move_to_end(key)
    return deepcopy(cached)


def clear_retrieval_cache() -> None:
    _RETRIEVAL_CACHE.clear()


def initial_retrieve(lexical_index, query: str, settings: Settings, k: int | None = None) -> List[Document]:
    """Perform BM25 retrieval over the locally indexed document chunks."""
    depth = k or settings.retrieval_top_k
    key = _cache_key(query, settings, depth, "bm25")
    cached = _cached_retrieval(key)
    if cached is not None:
        return cached
    documents = keyword_search(lexical_index, query, depth)
    _remember_retrieval(key, documents)
    return documents


def hybrid_retrieve(lexical_index, query: str, settings: Settings, plan: QueryPlan) -> tuple[List[Document], list[str]]:
    """Retrieve with BM25 over each query rewrite plus a pseudo-relevance feedback search.

    Returns the filtered candidates and the feedback terms that were added.
    """
    key = _cache_key("|".join(plan.rewritten_queries), settings, plan.top_k, "bm25-hybrid")
    cached = _cached_retrieval(key)
    if cached is not None:
        return cached

    per_query_k = max(plan.top_k, settings.retrieval_top_k)
    result_sets = [keyword_search(lexical_index, rewritten, per_query_k) for rewritten in plan.rewritten_queries]
    added_terms = feedback_terms(lexical_index, result_sets[0], exclude=set(tokenize(query)))
    if added_terms:
        result_sets.append(keyword_search(lexical_index, f"{query} {' '.join(added_terms)}", per_query_k, channel="feedback"))

    fused = reciprocal_rank_fusion(
        result_sets,
        k=max(plan.top_k * 3, plan.retrieval_top_n + 4),
    )
    fused = score_and_filter_candidates(query, fused, settings, plan)
    _remember_retrieval(key, (fused, added_terms))
    return fused, added_terms


def rank_documents(query: str, documents: List[Document], settings: Settings, top_n: int | None = None) -> List[Document]:
    """Apply deterministic lexical, phrase, metadata, and passage quality ranking."""
    if not documents:
        return []

    query_terms = set(tokenize(query))
    scored_documents = []
    for doc in documents:
        ranked = deepcopy(doc)
        text_terms = set(tokenize(ranked.page_content))
        lexical_overlap = len(query_terms & text_terms) / max(1, len(query_terms))
        bm25_norm = float(ranked.metadata.get("bm25_norm", 0.0))
        intent_boost = float(ranked.metadata.get("intent_boost", 0.0))
        metadata_boost = float(ranked.metadata.get("metadata_boost", 0.0))
        quality_score = float(ranked.metadata.get("quality_score", 0.0))
        final_score = (
            0.50 * bm25_norm
            + 0.22 * lexical_overlap
            + 0.10 * quality_score
            + intent_boost
            + metadata_boost
        )
        ranked.metadata["lexical_overlap"] = round(lexical_overlap, 4)
        ranked.metadata["relevance_score"] = round(max(0.0, min(1.0, final_score)), 4)
        ranked.metadata["final_fused_score"] = ranked.metadata["relevance_score"]
        ranked.metadata["retrieval_strategy"] = "BM25 lexical ranking"
        scored_documents.append(ranked)

    scored_documents.sort(key=lambda item: item.metadata.get("final_fused_score", 0.0), reverse=True)
    return scored_documents[: (top_n or settings.retrieval_top_n)]


def score_and_filter_candidates(query: str, documents: List[Document], settings: Settings, plan: QueryPlan) -> List[Document]:
    """Add deterministic lexical, phrase, metadata, and passage quality signals."""
    if not documents:
        return []

    query_terms = set(tokenize(query))
    phrases = query_phrases(query)
    scored = []
    for doc in documents:
        candidate = deepcopy(doc)
        text = candidate.page_content
        text_terms = set(tokenize(text))
        overlap = len(query_terms & text_terms) / max(1, len(query_terms))
        candidate.metadata["intent_boost"] = _phrase_boost(phrases, text)
        candidate.metadata["metadata_boost"] = _metadata_boost(query_terms, candidate)
        candidate.metadata["quality_score"] = _quality_score(text)
        candidate.metadata["lexical_overlap"] = round(overlap, 4)
        candidate.metadata["pre_rank_score"] = round(
            0.60 * float(candidate.metadata.get("bm25_norm", 0.0))
            + 0.25 * overlap
            + float(candidate.metadata["intent_boost"])
            + float(candidate.metadata["metadata_boost"])
            + 0.08 * float(candidate.metadata["quality_score"]),
            4,
        )
        if overlap > 0:
            scored.append(candidate)

    scored.sort(key=lambda item: item.metadata.get("pre_rank_score", 0.0), reverse=True)
    return scored[: max(plan.top_k, plan.retrieval_top_n + 2)]


def query_phrases(query: str) -> set[str]:
    """Adjacent word pairs from the query, skipping pairs that include a stopword."""
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", query.lower())
    return {
        normalize_phrase_text(f"{left} {right}").strip()
        for left, right in zip(words, words[1:])
        if left not in STOPWORDS and right not in STOPWORDS
    }


def _phrase_boost(phrases: set[str], text: str) -> float:
    if not phrases:
        return 0.0
    haystack = normalize_phrase_text(text)
    hits = sum(1 for phrase in phrases if f" {phrase} " in haystack)
    return round(min(0.30, 0.10 * hits), 4)


def _stem(term: str) -> str:
    return term[:-1] if len(term) > 4 and term.endswith("s") and not term.endswith("ss") else term


def _metadata_boost(query_terms: set[str], doc: Document) -> float:
    """Boost passages whose file name, title, or tags share words with the query."""
    if not query_terms:
        return 0.0
    source = str(doc.metadata.get("source", "")).replace("\\", "/")
    title = str(doc.metadata.get("title", ""))
    tags_value = doc.metadata.get("tags", [])
    tags = " ".join(str(item) for item in tags_value) if isinstance(tags_value, list) else str(tags_value)
    haystack = re.sub(r"[_\-.]+", " ", f"{Path(source).stem} {title} {tags}")
    name_terms = {_stem(term) for term in tokenize(haystack)}
    matched = sum(1 for term in query_terms if _stem(term) in name_terms)
    return round(min(0.25, 0.25 * matched / len(query_terms)), 4)


def _quality_score(text: str) -> float:
    lowered = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", lowered)
    if not words:
        return 0.0
    unique_ratio = len(set(words)) / len(words)
    definition_bonus = 0.2 if any(pattern in lowered for pattern in (" is ", " refers to ", " combines ", " architecture", " system that")) else 0.0
    boilerplate_penalty = 0.25 if any(term in lowered for term in ("import ", "from langchain", "example", "tutorial", "```")) else 0.0
    tiny_penalty = 0.15 if len(words) < 35 else 0.0
    return round(max(0.0, min(1.0, unique_ratio + definition_bonus - boilerplate_penalty - tiny_penalty)), 4)


def retrieve_adaptive(query: str, lexical_index, settings: Settings) -> tuple[list[Document], list[Document], dict]:
    """Classify the query and retrieve/rank evidence with the local BM25 index."""
    expansions = load_query_expansions(settings.query_expansions_path)
    plan = classify_query(query, settings.retrieval_top_k, settings.retrieval_top_n, expansions)
    search_start = perf_counter()
    initial_docs, added_terms = hybrid_retrieve(lexical_index, query, settings, plan)
    search_ms = (perf_counter() - search_start) * 1000
    ranking_start = perf_counter()
    ranked_docs = rank_documents(query, initial_docs, settings, top_n=plan.retrieval_top_n)
    ranking_ms = (perf_counter() - ranking_start) * 1000
    confidence = _retrieval_confidence(ranked_docs)
    trace = {
        "query_type": plan.query_type,
        "complexity": plan.complexity,
        "multi_hop": plan.multi_hop,
        "top_k": plan.top_k,
        "retrieval_top_n": plan.retrieval_top_n,
        "retrieval_strategy": "BM25 lexical ranking",
        "bm25_search_ms": round(search_ms, 3),
        "ranking_ms": round(ranking_ms, 3),
        "rewritten_queries": plan.rewritten_queries,
        "feedback_terms": added_terms,
        "retrieval_confidence": confidence,
        "retrieval_channels": _channels(ranked_docs),
        "corrective_attempts": [],
    }
    return initial_docs, ranked_docs, trace


def corrective_retrieve(query: str, lexical_index, settings: Settings, previous_trace: dict) -> tuple[list[Document], list[Document], dict]:
    """Retry with a wider search, expanding the query with terms from a deeper result pool."""
    pool = keyword_search(lexical_index, query, max(10, settings.retrieval_top_k * 3))
    added_terms = feedback_terms(lexical_index, pool, exclude=set(tokenize(query)), n_terms=8, n_docs=5)
    expansion = f"{query} {' '.join(added_terms)}" if added_terms else query

    expansions = load_query_expansions(settings.query_expansions_path)
    plan = classify_query(expansion, max(settings.retrieval_top_k, 6), max(settings.retrieval_top_n, 4), expansions)
    search_start = perf_counter()
    initial_docs, _feedback = hybrid_retrieve(lexical_index, expansion, settings, plan)
    search_ms = (perf_counter() - search_start) * 1000
    ranking_start = perf_counter()
    ranked_docs = rank_documents(query, initial_docs, settings, top_n=plan.retrieval_top_n)
    ranking_ms = (perf_counter() - ranking_start) * 1000
    retry_trace = {
        "rewrite": expansion,
        "top_k": plan.top_k,
        "retrieval_top_n": plan.retrieval_top_n,
        "retrieval_confidence": _retrieval_confidence(ranked_docs),
    }
    trace = {**previous_trace}
    trace["corrective_attempts"] = [*previous_trace.get("corrective_attempts", []), retry_trace]
    trace["retrieval_confidence"] = max(float(previous_trace.get("retrieval_confidence", 0.0)), retry_trace["retrieval_confidence"])
    trace["rewritten_queries"] = list(dict.fromkeys([*previous_trace.get("rewritten_queries", []), expansion]))
    trace["retrieval_channels"] = _channels(ranked_docs)
    trace["bm25_search_ms"] = round(search_ms, 3)
    trace["ranking_ms"] = round(ranking_ms, 3)
    return initial_docs, ranked_docs, trace


def _retrieval_confidence(documents: List[Document]) -> float:
    scores = [float(doc.metadata.get("final_fused_score", 0.0)) for doc in documents]
    return round(max(0.0, min(1.0, sum(scores) / len(scores))), 4) if scores else 0.0


def _channels(documents: List[Document]) -> list[str]:
    channels = set()
    for doc in documents:
        channels.update(doc.metadata.get("retrieval_channels", []))
    return sorted(channels)


def debug_retrieval(query: str, lexical_index, settings: Settings) -> Tuple[List[Document], List[Document]]:
    """Return initial and ranked documents for diagnostic endpoints."""
    initial_docs, ranked_docs, _trace = retrieve_adaptive(query, lexical_index, settings)
    return initial_docs, ranked_docs
