import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document


def all_documents(vector_store) -> list[Document]:
    store = getattr(vector_store, "docstore", None)
    docs = getattr(store, "_dict", {})
    return [doc for doc in docs.values() if isinstance(doc, Document)]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())


def keyword_search(vector_store, query: str, k: int) -> list[Document]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    query_set = set(query_terms)
    docs = all_documents(vector_store)
    doc_freq = {term: 0 for term in query_set}
    tokenized_docs = []
    for doc in docs:
        tokens = tokenize(doc.page_content)
        tokenized_docs.append((doc, tokens))
        token_set = set(tokens)
        for term in query_set:
            if term in token_set:
                doc_freq[term] += 1

    scored = []
    total_docs = max(1, len(docs))
    for doc, tokens in tokenized_docs:
        if not tokens:
            continue
        counts = {term: tokens.count(term) for term in query_set}
        score = 0.0
        for term, tf in counts.items():
            if tf <= 0:
                continue
            idf = math.log((total_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
            score += (tf / max(1, len(tokens))) * idf
        if score:
            result = deepcopy(doc)
            result.metadata["keyword_score"] = score
            scored.append(result)

    scored.sort(key=lambda item: item.metadata.get("keyword_score", 0.0), reverse=True)
    return scored[:k]


def priority_source_search(raw_data_dir: Path, query: str) -> list[Document]:
    """Inject high-priority raw sources when query intent explicitly matches them."""
    query_lower = query.lower()
    priority_files = []
    if "adaptive" in query_lower:
        priority_files.extend(["adaptive_rag.txt", "corrective_rag.txt", "self_reflective_rag.txt"])
    if "corrective" in query_lower:
        priority_files.append("corrective_rag.txt")

    documents = []
    for filename in dict.fromkeys(priority_files):
        path = raw_data_dir / filename
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        for index, chunk in enumerate(_chunk_text(text), start=1):
            doc = Document(
                page_content=chunk,
                metadata={
                    "source": str(path),
                    "priority_source": True,
                    "priority_rank": index,
                    "keyword_score": 1.0,
                    "keyword_norm": 1.0,
                    "vector_score": 0.65,
                    "vector_norm": 0.65,
                    "retrieval_channels": ["metadata", "keyword"],
                },
            )
            documents.append(doc)
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
    source_names = ("vector", "keyword", "metadata")
    for source_index, docs in enumerate(result_sets):
        source_name = source_names[source_index] if source_index < len(source_names) else f"source_{source_index}"
        for rank, doc in enumerate(docs, start=1):
            doc_id = _doc_id(doc)
            existing_doc, existing_score, channels = fused.get(doc_id, (deepcopy(doc), 0.0, set()))
            channels.add(source_name)
            score = existing_score + 1.0 / (rrf_k + rank)
            existing_doc.metadata.update(doc.metadata)
            if source_name == "vector":
                existing_doc.metadata["vector_rank"] = min(rank, int(existing_doc.metadata.get("vector_rank", rank)))
            if source_name == "keyword":
                existing_doc.metadata["keyword_rank"] = min(rank, int(existing_doc.metadata.get("keyword_rank", rank)))
            existing_doc.metadata["vector_score"] = max(
                float(existing_doc.metadata.get("vector_score", 0.0)),
                float(doc.metadata.get("vector_score", 0.0)),
            )
            existing_doc.metadata["keyword_score"] = max(
                float(existing_doc.metadata.get("keyword_score", 0.0)),
                float(doc.metadata.get("keyword_score", 0.0)),
            )
            existing_doc.metadata["rrf_score"] = score
            existing_doc.metadata["retrieval_channels"] = sorted(channels)
            fused[doc_id] = (existing_doc, score, channels)

    ranked = [item[0] for item in sorted(fused.values(), key=lambda item: item[1], reverse=True)]
    _normalize_metadata_scores(ranked, ("vector_score", "keyword_score", "rrf_score"))
    return ranked[:k]


def _normalize_metadata_scores(documents: list[Document], fields: tuple[str, ...]) -> None:
    for field in fields:
        values = [float(doc.metadata.get(field, 0.0)) for doc in documents]
        if not values:
            continue
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        normalized_field = field.replace("_score", "_norm")
        for doc in documents:
            value = float(doc.metadata.get(field, 0.0))
            doc.metadata[normalized_field] = 1.0 if span == 0 and value > 0 else ((value - minimum) / span if span else 0.0)


def _doc_id(doc: Document) -> str:
    source = str(doc.metadata.get("source", "unknown"))
    page = str(doc.metadata.get("page", ""))
    content_hash = hash(doc.page_content[:300])
    return f"{source}:{page}:{content_hash}"
