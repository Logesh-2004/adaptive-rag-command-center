from collections import OrderedDict
from copy import deepcopy
import re
from time import perf_counter
from typing import List, Tuple

from langchain_core.documents import Document

from app.core.config import Settings
from app.retrieval.hybrid import keyword_search, priority_source_search, reciprocal_rank_fusion, tokenize
from app.retrieval.query_classifier import QueryPlan, classify_query

_RETRIEVAL_CACHE: OrderedDict[tuple[str, int, str, str], List[Document]] = OrderedDict()
_MAX_RETRIEVAL_CACHE = 64


def _cache_key(query: str, settings: Settings, k: int, mode: str) -> tuple[str, int, str, str]:
    return (query.strip().lower(), k, str(settings.lexical_index_path), mode)


def _remember_retrieval(key: tuple[str, int, str, str], documents: List[Document]) -> None:
    _RETRIEVAL_CACHE[key] = deepcopy(documents)
    _RETRIEVAL_CACHE.move_to_end(key)
    while len(_RETRIEVAL_CACHE) > _MAX_RETRIEVAL_CACHE:
        _RETRIEVAL_CACHE.popitem(last=False)


def clear_retrieval_cache() -> None:
    _RETRIEVAL_CACHE.clear()


def initial_retrieve(lexical_index, query: str, settings: Settings, k: int | None = None) -> List[Document]:
    """Perform BM25 retrieval over the locally indexed document chunks."""
    depth = k or settings.retrieval_top_k
    key = _cache_key(query, settings, depth, "bm25")
    cached = _RETRIEVAL_CACHE.get(key)
    if cached is not None:
        _RETRIEVAL_CACHE.move_to_end(key)
        return deepcopy(cached)
    documents = keyword_search(lexical_index, query, depth)
    _remember_retrieval(key, documents)
    return documents


def hybrid_retrieve(lexical_index, query: str, settings: Settings, plan: QueryPlan) -> List[Document]:
    """Retrieve with local BM25 search plus targeted source matches."""
    key = _cache_key("|".join(plan.rewritten_queries), settings, plan.top_k, "bm25-hybrid")
    cached = _RETRIEVAL_CACHE.get(key)
    if cached is not None:
        _RETRIEVAL_CACHE.move_to_end(key)
        return deepcopy(cached)

    result_sets: list[list[Document]] = []
    per_query_k = max(plan.top_k, settings.retrieval_top_k)
    for rewritten in plan.rewritten_queries:
        result_sets.append(keyword_search(lexical_index, rewritten, per_query_k))
    result_sets.append(priority_source_search(settings.raw_data_dir, query))

    fused = reciprocal_rank_fusion(
        result_sets,
        k=max(plan.top_k * 3, plan.retrieval_top_n + 4),
    )
    fused = score_and_filter_candidates(query, fused, settings, plan)
    _remember_retrieval(key, fused)
    return fused


def rank_documents(query: str, documents: List[Document], settings: Settings, top_n: int | None = None) -> List[Document]:
    """Apply deterministic lexical, intent, metadata, and passage quality ranking."""
    if not documents:
        return []

    scored_documents = []
    for doc in documents:
        ranked = deepcopy(doc)
        text = ranked.page_content
        query_terms = set(tokenize(query))
        text_terms = set(tokenize(text))
        lexical_overlap = len(query_terms & text_terms) / max(1, len(query_terms))
        bm25_norm = float(ranked.metadata.get("bm25_norm", 0.0))
        intent_boost = float(ranked.metadata.get("intent_boost", 0.0))
        metadata_boost = float(ranked.metadata.get("metadata_boost", 0.0))
        quality_score = float(ranked.metadata.get("quality_score", 0.0))
        priority_boost = 0.12 if ranked.metadata.get("priority_source") else 0.0
        final_score = (
            0.50 * bm25_norm
            + 0.22 * lexical_overlap
            + 0.10 * quality_score
            + intent_boost
            + metadata_boost
            + priority_boost
        )
        ranked.metadata["lexical_overlap"] = round(lexical_overlap, 4)
        ranked.metadata["relevance_score"] = round(max(0.0, min(1.0, final_score)), 4)
        ranked.metadata["final_fused_score"] = ranked.metadata["relevance_score"]
        ranked.metadata["retrieval_strategy"] = "BM25 lexical ranking"
        scored_documents.append(ranked)

    scored_documents.sort(key=lambda item: item.metadata.get("final_fused_score", 0.0), reverse=True)
    return scored_documents[: (top_n or settings.retrieval_top_n)]


def score_and_filter_candidates(query: str, documents: List[Document], settings: Settings, plan: QueryPlan) -> List[Document]:
    """Add deterministic lexical, intent, metadata, and passage quality signals."""
    if not documents:
        return []

    query_terms = set(tokenize(query))
    scored = []
    for doc in documents:
        candidate = deepcopy(doc)
        text = candidate.page_content
        text_terms = set(tokenize(text))
        overlap = len(query_terms & text_terms) / max(1, len(query_terms))
        candidate.metadata["intent_boost"] = _intent_boost(query, text, _critical_terms(query))
        candidate.metadata["metadata_boost"] = _metadata_boost(query, candidate)
        candidate.metadata["quality_score"] = _quality_score(query, text)
        candidate.metadata["lexical_overlap"] = round(overlap, 4)
        candidate.metadata["pre_rank_score"] = round(
            0.60 * float(candidate.metadata.get("bm25_norm", 0.0))
            + 0.25 * overlap
            + float(candidate.metadata["intent_boost"])
            + float(candidate.metadata["metadata_boost"])
            + 0.08 * float(candidate.metadata["quality_score"]),
            4,
        )
        if overlap > 0 or candidate.metadata.get("priority_source"):
            scored.append(candidate)

    scored.sort(key=lambda item: item.metadata.get("pre_rank_score", 0.0), reverse=True)
    return scored[: max(plan.top_k, plan.retrieval_top_n + 2)]


def _critical_terms(query: str) -> set[str]:
    terms = {"adaptive", "corrective", "agentic", "self-reflective", "self reflective", "multimodal"}
    lowered = query.lower()
    return {term for term in terms if term in lowered}


def _intent_boost(query: str, text: str, critical_terms: set[str]) -> float:
    lowered_text = text.lower()
    boost = 0.0
    for term in critical_terms:
        normalized = term.replace("-", " ")
        if term in lowered_text or normalized in lowered_text:
            boost += 0.10
    if "adaptive rag" in query.lower() and ("adaptive retrieval" in lowered_text or "adaptive rag" in lowered_text):
        boost += 0.12
    if "adaptive rag" in query.lower() and "rag" in lowered_text and "adaptive" not in lowered_text:
        boost -= 0.05
    return round(max(-0.10, min(0.30, boost)), 4)


def _metadata_boost(query: str, doc: Document) -> float:
    source = str(doc.metadata.get("source", "")).lower().replace("\\", "/")
    title = str(doc.metadata.get("title", "")).lower()
    tags_value = doc.metadata.get("tags", [])
    tags = " ".join(str(item).lower() for item in tags_value) if isinstance(tags_value, list) else str(tags_value).lower()
    haystack = f"{source} {title} {tags}"
    query_lower = query.lower()
    boost = 0.0
    if "adaptive" in query_lower and "adaptive_rag" in haystack:
        boost += 0.18
    if "adaptive" in query_lower and "adaptive" in haystack:
        boost += 0.08
    if "corrective" in query_lower and "corrective" in haystack:
        boost += 0.12
    return round(min(0.25, boost), 4)


def _quality_score(query: str, text: str) -> float:
    lowered = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", lowered)
    if not words:
        return 0.0
    unique_ratio = len(set(words)) / len(words)
    definition_bonus = 0.2 if any(pattern in lowered for pattern in (" is ", " refers to ", " combines ", " architecture", " system that")) else 0.0
    adaptive_bonus = 0.15 if "adaptive" in query.lower() and "adaptive" in lowered else 0.0
    boilerplate_penalty = 0.25 if any(term in lowered for term in ("import ", "from langchain", "example", "tutorial", "```")) else 0.0
    tiny_penalty = 0.15 if len(words) < 35 else 0.0
    return round(max(0.0, min(1.0, unique_ratio + definition_bonus + adaptive_bonus - boilerplate_penalty - tiny_penalty)), 4)


def retrieve_adaptive(query: str, lexical_index, settings: Settings) -> tuple[list[Document], list[Document], dict]:
    """Classify the query and retrieve/rank evidence with the local BM25 index."""
    plan = classify_query(query, settings.retrieval_top_k, settings.retrieval_top_n)
    search_start = perf_counter()
    initial_docs = hybrid_retrieve(lexical_index, query, settings, plan)
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
        "retrieval_confidence": confidence,
        "retrieval_channels": _channels(ranked_docs),
        "corrective_attempts": [],
    }
    return initial_docs, ranked_docs, trace


def corrective_retrieve(query: str, lexical_index, settings: Settings, previous_trace: dict) -> tuple[list[Document], list[Document], dict]:
    """Retry keyword retrieval with a deterministic concept expansion."""
    if "adaptive rag" in query.lower():
        expansion = query + " adaptive retrieval feedback reranking self evaluation hallucination mitigation"
    elif "rag" in query.lower():
        expansion = query + " retrieval augmented generation grounding corrective retrieval"
    else:
        expansion = query + " related concepts evidence explanation"

    plan = classify_query(expansion, max(settings.retrieval_top_k, 6), max(settings.retrieval_top_n, 4))
    search_start = perf_counter()
    initial_docs = hybrid_retrieve(lexical_index, expansion, settings, plan)
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
    trace.setdefault("corrective_attempts", []).append(retry_trace)
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
