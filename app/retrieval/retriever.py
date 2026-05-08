from collections import OrderedDict
from copy import deepcopy
import math
import re
from typing import List, Tuple
from langchain_core.documents import Document

from app.core.config import Settings
from app.retrieval.hybrid import keyword_search, priority_source_search, reciprocal_rank_fusion
from app.retrieval.query_classifier import QueryPlan, classify_query
from app.retrieval.vector_store import get_embeddings, query_vector_store

_RETRIEVAL_CACHE: OrderedDict[tuple[str, int, str, str], List[Document]] = OrderedDict()
_MAX_RETRIEVAL_CACHE = 64
_CROSS_ENCODERS = {}


def _cache_key(query: str, settings: Settings, k: int, mode: str) -> tuple[str, int, str, str]:
    return (query.strip().lower(), k, str(settings.vector_db_path), mode)


def _remember_retrieval(key: tuple[str, int, str, str], documents: List[Document]) -> None:
    _RETRIEVAL_CACHE[key] = deepcopy(documents)
    _RETRIEVAL_CACHE.move_to_end(key)
    while len(_RETRIEVAL_CACHE) > _MAX_RETRIEVAL_CACHE:
        _RETRIEVAL_CACHE.popitem(last=False)


def clear_retrieval_cache() -> None:
    _RETRIEVAL_CACHE.clear()


def initial_retrieve(vector_store, query: str, settings: Settings, k: int | None = None) -> List[Document]:
    """Perform an initial FAISS retrieval over the vector store."""
    depth = k or settings.retrieval_top_k
    key = _cache_key(query, settings, depth, "vector")
    cached = _RETRIEVAL_CACHE.get(key)
    if cached is not None:
        _RETRIEVAL_CACHE.move_to_end(key)
        return deepcopy(cached)
    documents = query_vector_store(vector_store, query, k=depth)
    _remember_retrieval(key, documents)
    return documents


def hybrid_retrieve(vector_store, query: str, settings: Settings, plan: QueryPlan) -> List[Document]:
    """Retrieve candidates with vector search, keyword search, and RRF fusion."""
    key = _cache_key("|".join(plan.rewritten_queries), settings, plan.top_k, "hybrid")
    cached = _RETRIEVAL_CACHE.get(key)
    if cached is not None:
        _RETRIEVAL_CACHE.move_to_end(key)
        return deepcopy(cached)

    vector_docs: list[Document] = []
    keyword_docs: list[Document] = []
    priority_docs: list[Document] = []
    per_query_k = max(plan.top_k, settings.retrieval_top_k)
    for rewritten in plan.rewritten_queries:
        vector_docs.extend(query_vector_store(vector_store, rewritten, k=per_query_k))
        keyword_docs.extend(keyword_search(vector_store, rewritten, k=per_query_k))
        priority_docs.extend(priority_source_search(settings.raw_data_dir, rewritten))

    fused = reciprocal_rank_fusion([vector_docs, keyword_docs, priority_docs], k=max(plan.top_k * 3, plan.rerank_top_n + 4))
    fused = score_and_filter_candidates(query, fused, settings, plan)
    _remember_retrieval(key, fused)
    return fused


def get_cross_encoder(settings: Settings):
    """Return a cached local CrossEncoder reranker."""
    if settings.rerank_model not in _CROSS_ENCODERS:
        from sentence_transformers import CrossEncoder

        try:
            _CROSS_ENCODERS[settings.rerank_model] = CrossEncoder(settings.rerank_model, local_files_only=True)
        except Exception:
            _CROSS_ENCODERS[settings.rerank_model] = CrossEncoder(settings.rerank_model)
    return _CROSS_ENCODERS[settings.rerank_model]


def _score_to_probability(score: float) -> float:
    try:
        import math

        return 1.0 / (1.0 + math.exp(-float(score)))
    except OverflowError:
        return 0.0 if score < 0 else 1.0


def rerank_documents(query: str, documents: List[Document], settings: Settings, top_n: int | None = None) -> List[Document]:
    """Rerank retrieved documents with a local cross-encoder, not an LLM."""
    if not documents:
        return []

    pairs = [(query, " ".join(doc.page_content.split())[:900]) for doc in documents]
    scores = get_cross_encoder(settings).predict(pairs)
    scored_documents = []
    for doc, score in zip(documents, scores):
        reranked = deepcopy(doc)
        raw_score = float(score)
        reranked.metadata["rerank_score"] = raw_score
        reranked.metadata["relevance_score"] = _score_to_probability(raw_score)
        reranked.metadata["rerank_model"] = settings.rerank_model
        scored_documents.append(reranked)

    _normalize_field(scored_documents, "relevance_score", "rerank_norm")
    for doc in scored_documents:
        vector_norm = float(doc.metadata.get("vector_norm", 0.0))
        keyword_norm = float(doc.metadata.get("keyword_norm", 0.0))
        rerank_norm = float(doc.metadata.get("rerank_norm", 0.0))
        metadata_boost = float(doc.metadata.get("metadata_boost", 0.0))
        intent_boost = float(doc.metadata.get("intent_boost", 0.0))
        quality_score = float(doc.metadata.get("quality_score", 0.0))
        semantic_similarity = float(doc.metadata.get("semantic_similarity", 0.0))
        final_score = (
            0.5 * vector_norm
            + 0.2 * keyword_norm
            + 0.3 * rerank_norm
            + metadata_boost
            + intent_boost
            + 0.08 * quality_score
            + 0.12 * semantic_similarity
        )
        doc.metadata["final_fused_score"] = round(max(0.0, min(1.0, final_score)), 4)

    scored_documents.sort(key=lambda item: item.metadata.get("final_fused_score", 0.0), reverse=True)
    return scored_documents[: (top_n or settings.rerank_top_n)]


def score_and_filter_candidates(query: str, documents: List[Document], settings: Settings, plan: QueryPlan) -> List[Document]:
    """Apply semantic filtering, intent boosts, metadata boosts, and quality scoring before reranking."""
    if not documents:
        return []

    query_vector = get_embeddings(settings).embed_query(query)
    scored = []
    critical_terms = _critical_terms(query)
    semantic_floor = 0.18 if plan.query_type == "factual" else 0.14
    for doc in documents:
        candidate = deepcopy(doc)
        text = candidate.page_content
        semantic_similarity = _cosine(query_vector, get_embeddings(settings).embed_query(text[:1200]))
        candidate.metadata["semantic_similarity"] = round(semantic_similarity, 4)
        candidate.metadata["intent_boost"] = _intent_boost(query, text, critical_terms)
        candidate.metadata["metadata_boost"] = _metadata_boost(query, candidate)
        candidate.metadata["quality_score"] = _quality_score(query, text)
        candidate.metadata["specificity_score"] = _specificity_score(query, text, candidate)
        candidate.metadata["pre_rerank_score"] = round(
            0.5 * float(candidate.metadata.get("vector_norm", 0.0))
            + 0.2 * float(candidate.metadata.get("keyword_norm", 0.0))
            + 0.15 * semantic_similarity
            + float(candidate.metadata["intent_boost"])
            + float(candidate.metadata["metadata_boost"])
            + 0.08 * float(candidate.metadata["quality_score"]),
            4,
        )
        if semantic_similarity >= semantic_floor or candidate.metadata["intent_boost"] > 0 or candidate.metadata["metadata_boost"] > 0:
            scored.append(candidate)

    scored.sort(key=lambda item: item.metadata.get("pre_rerank_score", 0.0), reverse=True)
    return scored[: max(plan.top_k, plan.rerank_top_n + 2)]


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
            boost += 0.18
    if "adaptive rag" in query.lower() and ("adaptive retrieval" in lowered_text or "adaptive rag" in lowered_text):
        boost += 0.25
    if "adaptive rag" in query.lower() and "rag" in lowered_text and "adaptive" not in lowered_text:
        boost -= 0.08
    return round(max(-0.12, min(0.45, boost)), 4)


def _metadata_boost(query: str, doc: Document) -> float:
    source = str(doc.metadata.get("source", "")).lower().replace("\\", "/")
    title = str(doc.metadata.get("title", "")).lower()
    tags = " ".join(str(item).lower() for item in doc.metadata.get("tags", [])) if isinstance(doc.metadata.get("tags"), list) else str(doc.metadata.get("tags", "")).lower()
    haystack = f"{source} {title} {tags}"
    query_lower = query.lower()
    boost = 0.0
    if "adaptive" in query_lower and "adaptive_rag" in haystack:
        boost += 0.42
    if "adaptive" in query_lower and "adaptive" in haystack:
        boost += 0.20
    if "corrective" in query_lower and "corrective" in haystack:
        boost += 0.25
    if "langchain" in haystack and "langchain" not in query_lower:
        boost -= 0.12
    return round(max(-0.2, min(0.5, boost)), 4)


def _quality_score(query: str, text: str) -> float:
    lowered = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", lowered)
    if not words:
        return 0.0
    unique_ratio = len(set(words)) / len(words)
    definition_bonus = 0.2 if any(pattern in lowered for pattern in (" is ", " refers to ", " combines ", " architecture", " system that")) else 0.0
    adaptive_bonus = 0.2 if "adaptive" in query.lower() and "adaptive" in lowered else 0.0
    boilerplate_penalty = 0.25 if any(term in lowered for term in ("import ", "from langchain", "example", "tutorial", "```")) else 0.0
    tiny_penalty = 0.15 if len(words) < 35 else 0.0
    return round(max(0.0, min(1.0, unique_ratio + definition_bonus + adaptive_bonus - boilerplate_penalty - tiny_penalty)), 4)


def _specificity_score(query: str, text: str, doc: Document) -> float:
    query_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", query.lower()))
    text_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower()))
    source = str(doc.metadata.get("source", "")).lower()
    overlap = len(query_terms & text_terms) / max(1, len(query_terms))
    source_match = 0.25 if any(term in source for term in query_terms) else 0.0
    return round(min(1.0, overlap + source_match), 4)


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _normalize_field(documents: List[Document], field: str, normalized_field: str) -> None:
    values = [float(doc.metadata.get(field, 0.0)) for doc in documents]
    if not values:
        return
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    for doc in documents:
        value = float(doc.metadata.get(field, 0.0))
        doc.metadata[normalized_field] = 1.0 if span == 0 and value > 0 else ((value - minimum) / span if span else 0.0)


def retrieve_adaptive(query: str, vector_store, settings: Settings) -> tuple[list[Document], list[Document], dict]:
    """Classify, hybrid-retrieve, rerank, and return an observability trace."""
    plan = classify_query(query, settings.retrieval_top_k, settings.rerank_top_n)
    initial_docs = hybrid_retrieve(vector_store, query, settings, plan)
    reranked_docs = rerank_documents(query, initial_docs, settings, top_n=plan.rerank_top_n)
    confidence = _retrieval_confidence(reranked_docs)
    trace = {
        "query_type": plan.query_type,
        "complexity": plan.complexity,
        "multi_hop": plan.multi_hop,
        "top_k": plan.top_k,
        "rerank_top_n": plan.rerank_top_n,
        "rewritten_queries": plan.rewritten_queries,
        "retrieval_confidence": confidence,
        "retrieval_channels": _channels(reranked_docs),
        "corrective_attempts": [],
    }
    return initial_docs, reranked_docs, trace


def corrective_retrieve(query: str, vector_store, settings: Settings, previous_trace: dict) -> tuple[list[Document], list[Document], dict]:
    """Retry retrieval with expanded query semantics when confidence is weak."""
    expansion = query
    if "adaptive rag" in query.lower():
        expansion = query + " adaptive retrieval feedback reranking self evaluation hallucination mitigation"
    elif "rag" in query.lower():
        expansion = query + " retrieval augmented generation grounding corrective retrieval"
    else:
        expansion = query + " related concepts evidence explanation"

    plan = classify_query(expansion, max(settings.retrieval_top_k, 6), max(settings.rerank_top_n, 4))
    initial_docs = hybrid_retrieve(vector_store, expansion, settings, plan)
    reranked_docs = rerank_documents(query, initial_docs, settings, top_n=plan.rerank_top_n)
    retry_trace = {
        "rewrite": expansion,
        "top_k": plan.top_k,
        "rerank_top_n": plan.rerank_top_n,
        "retrieval_confidence": _retrieval_confidence(reranked_docs),
    }
    trace = {**previous_trace}
    trace.setdefault("corrective_attempts", []).append(retry_trace)
    trace["retrieval_confidence"] = max(float(previous_trace.get("retrieval_confidence", 0.0)), retry_trace["retrieval_confidence"])
    trace["rewritten_queries"] = list(dict.fromkeys([*previous_trace.get("rewritten_queries", []), expansion]))
    trace["retrieval_channels"] = _channels(reranked_docs)
    return initial_docs, reranked_docs, trace


def _retrieval_confidence(documents: List[Document]) -> float:
    scores = [float(doc.metadata.get("final_fused_score", 0.0)) for doc in documents if doc.metadata.get("final_fused_score") is not None]
    if not scores:
        scores = [float(doc.metadata.get("relevance_score", 0.0)) for doc in documents if doc.metadata.get("relevance_score") is not None]
    if not scores:
        scores = [float(doc.metadata.get("rrf_score", 0.0)) * 60 for doc in documents]
    return round(max(0.0, min(1.0, sum(scores) / len(scores))), 4) if scores else 0.0


def _channels(documents: List[Document]) -> list[str]:
    channels = set()
    for doc in documents:
        channels.update(doc.metadata.get("retrieval_channels", []))
    return sorted(channels)


def debug_retrieval(query: str, vector_store, settings: Settings) -> Tuple[List[Document], List[Document]]:
    """Return initial and reranked document sets for diagnostic endpoints."""
    initial_docs, reranked_docs, _trace = retrieve_adaptive(query, vector_store, settings)
    return initial_docs, reranked_docs
