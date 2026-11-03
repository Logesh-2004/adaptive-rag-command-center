import hashlib
import heapq
from collections import Counter
from copy import deepcopy
from typing import Iterable

from langchain_core.documents import Document

from app.retrieval.lexical_index import BM25Store
from app.retrieval.text import tokenize

__all__ = ["feedback_terms", "keyword_search", "reciprocal_rank_fusion", "tokenize"]


def keyword_search(lexical_index: BM25Store, query: str, k: int, channel: str = "bm25") -> list[Document]:
    """Rank chunks with BM25, reading only the postings of the query terms."""
    query_terms = set(tokenize(query))
    documents = lexical_index.documents
    if not query_terms or not documents:
        return []

    stats = lexical_index.stats
    k1, b = 1.5, 0.75
    scores: dict[int, float] = {}
    for term in query_terms:
        postings = stats.postings.get(term)
        if not postings:
            continue
        inverse_frequency = stats.idf(term)
        for index, frequency in postings:
            length_norm = frequency + k1 * (1.0 - b + b * stats.doc_lengths[index] / max(1.0, stats.average_length))
            scores[index] = scores.get(index, 0.0) + inverse_frequency * frequency * (k1 + 1.0) / length_norm

    results: list[Document] = []
    for index, score in heapq.nlargest(k, scores.items(), key=lambda item: item[1]):
        source = documents[index]
        result = Document(page_content=source.page_content, metadata=dict(source.metadata))
        result.metadata["bm25_score"] = round(score, 6)
        result.metadata["retrieval_channels"] = [channel]
        results.append(result)
    return results


def feedback_terms(
    lexical_index: BM25Store,
    documents: list[Document],
    exclude: set[str],
    n_terms: int = 5,
    n_docs: int = 3,
) -> list[str]:
    """Pick distinctive terms shared by the top results (pseudo-relevance feedback)."""
    stats = lexical_index.stats
    top_docs = documents[:n_docs]
    # A term must appear in at least two top results, so one off-topic hit cannot steer the expansion.
    min_presence = min(2, len(top_docs))
    weights: Counter[str] = Counter()
    presence: Counter[str] = Counter()
    for doc in top_docs:
        counts = Counter(tokenize(doc.page_content))
        length = sum(counts.values()) or 1
        for term, frequency in counts.items():
            # Terms found in a single chunk are usually names or noise rather than shared concepts.
            if term in exclude or len(term) < 4 or stats.document_frequency(term) < 2:
                continue
            weights[term] += (frequency / length) * stats.idf(term)
            presence[term] += 1
    ranked = [term for term, _weight in weights.most_common() if presence[term] >= min_presence]
    return ranked[:n_terms]


def reciprocal_rank_fusion(result_sets: Iterable[list[Document]], k: int, rrf_k: int = 60) -> list[Document]:
    """Fuse result lists by rank.

    Raw BM25 scores grow with query length, so each list's scores are first scaled to its
    own best hit. Only "bm25" lists count toward a passage's BM25 strength: the feedback
    list adds recall through its rank, but its extra terms must not inflate scores.
    """
    fused: dict[str, tuple[Document, float, set[str]]] = {}
    for docs in result_sets:
        list_max = max((float(doc.metadata.get("bm25_score", 0.0)) for doc in docs), default=0.0)
        for rank, doc in enumerate(docs, start=1):
            doc_id = _doc_id(doc)
            existing_doc, existing_score, channels = fused.get(doc_id, (deepcopy(doc), 0.0, set()))
            doc_channels = doc.metadata.get("retrieval_channels") or ["bm25"]
            channels.update(doc_channels)
            score = existing_score + 1.0 / (rrf_k + rank)
            best_raw = float(existing_doc.metadata.get("bm25_score", 0.0)) if existing_score else 0.0
            best_relative = float(existing_doc.metadata.get("bm25_relative_score", 0.0)) if existing_score else 0.0
            if "bm25" in doc_channels:
                best_raw = max(best_raw, float(doc.metadata.get("bm25_score", 0.0)))
                if list_max > 0:
                    best_relative = max(best_relative, float(doc.metadata.get("bm25_score", 0.0)) / list_max)
            existing_doc.metadata.update(doc.metadata)
            existing_doc.metadata["bm25_score"] = round(best_raw, 6)
            existing_doc.metadata["bm25_relative_score"] = round(best_relative, 6)
            existing_doc.metadata["rrf_score"] = score
            existing_doc.metadata["retrieval_channels"] = sorted(channels)
            fused[doc_id] = (existing_doc, score, channels)

    ranked = [item[0] for item in sorted(fused.values(), key=lambda item: item[1], reverse=True)]
    _normalize_metadata_scores(ranked, ("bm25_relative_score", "rrf_score"))
    for doc in ranked:
        doc.metadata["bm25_norm"] = doc.metadata.pop("bm25_relative_norm", 0.0)
    return ranked[:k]


def _normalize_metadata_scores(documents: list[Document], fields: tuple[str, ...]) -> None:
    for field in fields:
        values = [float(doc.metadata.get(field, 0.0)) for doc in documents]
        if not values:
            continue
        minimum, maximum = min(values), max(values)
        span = maximum - minimum
        normalized_field = field.replace("_score", "_norm")
        for doc in documents:
            value = float(doc.metadata.get(field, 0.0))
            doc.metadata[normalized_field] = 1.0 if span == 0 and value > 0 else ((value - minimum) / span if span else 0.0)


def _doc_id(doc: Document) -> str:
    source = str(doc.metadata.get("source", "unknown"))
    page = str(doc.metadata.get("page", ""))
    content_hash = hashlib.sha1(doc.page_content[:300].encode("utf-8")).hexdigest()
    return f"{source}:{page}:{content_hash}"
