import hashlib
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "was", "what", "when", "where", "which",
    "who", "why", "with",
}


def all_documents(lexical_index) -> list[Document]:
    return [doc for doc in getattr(lexical_index, "documents", []) if isinstance(doc, Document)]


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.lower()) if token not in _STOPWORDS]


def keyword_search(lexical_index, query: str, k: int) -> list[Document]:
    """Rank chunks with BM25, using only the locally indexed text."""
    query_terms = tokenize(query)
    documents = all_documents(lexical_index)
    if not query_terms or not documents:
        return []

    tokenized_docs = [tokenize(doc.page_content) for doc in documents]
    average_length = sum(map(len, tokenized_docs)) / max(1, len(tokenized_docs))
    query_term_set = set(query_terms)
    document_frequency = {
        term: sum(1 for tokens in tokenized_docs if term in set(tokens))
        for term in query_term_set
    }

    scored: list[Document] = []
    k1, b = 1.5, 0.75
    total_docs = len(documents)
    for doc, tokens in zip(documents, tokenized_docs):
        if not tokens:
            continue
        term_counts: dict[str, int] = {}
        for term in tokens:
            if term in query_term_set:
                term_counts[term] = term_counts.get(term, 0) + 1
        score = 0.0
        for term, frequency in term_counts.items():
            df = document_frequency[term]
            inverse_frequency = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            length_norm = frequency + k1 * (1.0 - b + b * len(tokens) / max(1.0, average_length))
            score += inverse_frequency * frequency * (k1 + 1.0) / length_norm
        if score > 0:
            result = deepcopy(doc)
            result.metadata["bm25_score"] = round(score, 6)
            result.metadata["retrieval_channels"] = ["bm25"]
            scored.append(result)

    scored.sort(key=lambda item: item.metadata.get("bm25_score", 0.0), reverse=True)
    return scored[:k]


def priority_source_search(raw_data_dir: Path, query: str) -> list[Document]:
    """Add selected RAG concept files when the query explicitly names them."""
    query_lower = query.lower()
    priority_files = []
    if "adaptive" in query_lower:
        priority_files.extend(["adaptive_rag.txt", "corrective_rag.txt", "self_reflective_rag.txt"])
    if "corrective" in query_lower:
        priority_files.append("corrective_rag.txt")

    documents = []
    for filename in dict.fromkeys(priority_files):
        path = raw_data_dir / filename
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        for index, chunk in enumerate(_chunk_text(text), start=1):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": str(path),
                        "priority_source": True,
                        "priority_rank": index,
                        "retrieval_channels": ["priority_source"],
                    },
                )
            )
    return documents


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks[:4]


def reciprocal_rank_fusion(result_sets: Iterable[list[Document]], k: int, rrf_k: int = 60) -> list[Document]:
    fused: dict[str, tuple[Document, float, set[str]]] = {}
    for docs in result_sets:
        for rank, doc in enumerate(docs, start=1):
            source_name = "priority_source" if doc.metadata.get("priority_source") else "bm25"
            doc_id = _doc_id(doc)
            existing_doc, existing_score, channels = fused.get(doc_id, (deepcopy(doc), 0.0, set()))
            channels.add(source_name)
            score = existing_score + 1.0 / (rrf_k + rank)
            best_bm25_score = max(
                float(existing_doc.metadata.get("bm25_score", 0.0)),
                float(doc.metadata.get("bm25_score", 0.0)),
            )
            existing_doc.metadata.update(doc.metadata)
            if best_bm25_score:
                existing_doc.metadata["bm25_score"] = best_bm25_score
            existing_doc.metadata["rrf_score"] = score
            existing_doc.metadata["retrieval_channels"] = sorted(channels)
            fused[doc_id] = (existing_doc, score, channels)

    ranked = [item[0] for item in sorted(fused.values(), key=lambda item: item[1], reverse=True)]
    _normalize_metadata_scores(ranked, ("bm25_score", "rrf_score"))
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
